"""
DataScheduler — database/export_import.py
Export d'un pipeline vers un bundle JSON versionné et portable (chantier 5a).

L'import (lecture, détection de collision par UUID, remappage de profils) est un chantier séparé
(5b) — ce module ne couvre que l'export, mais la forme du bundle est conçue pour lui : chaque
référence de profil/requête dans un config_json est traduite en UUID (jamais un id entier local,
sans signification sur une autre machine), et chaque entité portée a sa propre identité stable
(voir database/models.py, chantier 2).

Secrets : liste explicite de champs "critiques" (uniquement `password`), jamais une heuristique —
chiffrés avec une clé Fernet dérivée du mot de passe fourni à l'export (PBKDF2-HMAC-SHA256, sel
aléatoire stocké en clair dans le bundle — pas secret, nécessaire pour rederiver la même clé à
l'import). Différent de la clé maître locale (database/crypto.py, chantier 1) : celle-ci est liée
au compte Windows de la machine et ne peut pas servir à un fichier destiné à circuler. Si aucun mot
de passe n'est fourni, les mots de passe sont omis du bundle plutôt que forcés — cas d'usage
légitime : partager la structure d'un pipeline sans les identifiants.
"""

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import crypto, db_manager as db
from .models import DbType, FtpProtocol
from version import __version__

CURRENT_SCHEMA_VERSION = 1   # forme du bundle — indépendant de __version__, bump seulement si ça change
_KDF_ITERATIONS = 600_000

# Références de profil/requête connues par type d'étape : (clé_config, type_référence).
# Seuls les steps qui consomment un profil/une requête réutilisable y figurent.
_STEP_REFERENCES = {
    "DB_EXTRACT":   [("profile_id", "db_profile"), ("sql_query_id", "sql_query")],
    "DB_EXECUTE":   [("profile_id", "db_profile"), ("sql_query_id", "sql_query")],
    "DB_LOAD":      [("profile_id", "db_profile")],
    "FTP_UPLOAD":   [("ftp_profile_id", "ftp_profile")],
    "FTP_DOWNLOAD": [("ftp_profile_id", "ftp_profile")],
    "EMAIL_NOTIFY": [("smtp_profile_id", "smtp_profile")],
}

_UUID_KEY_FOR = {
    "profile_id":      "profile_uuid",
    "ftp_profile_id":  "ftp_profile_uuid",
    "sql_query_id":    "sql_query_uuid",
    "smtp_profile_id": "smtp_profile_uuid",
}


@dataclass
class ExportResult:
    success:  bool
    bundle:   dict | None = None
    warnings: list        = field(default_factory=list)
    error:    str | None  = None


# ──────────────────────────────────────────────
#  CHIFFREMENT SPÉCIFIQUE À L'EXPORT (KDF depuis un mot de passe fourni)
# ──────────────────────────────────────────────

def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_KDF_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _new_export_cipher(password: str) -> tuple[Fernet, dict]:
    salt = os.urandom(16)
    fernet = Fernet(_derive_key(password, salt))
    kdf_meta = {
        "algorithm": "pbkdf2_sha256",
        "salt": base64.b64encode(salt).decode("ascii"),
        "iterations": _KDF_ITERATIONS,
    }
    return fernet, kdf_meta


def _serialize_password(local_ciphertext: str | None, export_fernet: Fernet | None) -> dict:
    """
    local_ciphertext : la valeur telle que stockée en base (déjà chiffrée avec la clé maître
    locale, chantier 1) — jamais réutilisée telle quelle dans le bundle, toujours déchiffrée puis
    rechiffrée avec la clé d'export si un mot de passe d'export a été fourni.
    """
    if not local_ciphertext or export_fernet is None:
        return {"password_status": "omitted"}
    plain = crypto.decrypt(local_ciphertext)
    encrypted = export_fernet.encrypt(plain.encode("utf-8")).decode("ascii")
    return {"password_status": "encrypted", "encrypted_password": encrypted}


# ──────────────────────────────────────────────
#  RÉSOLUTION DES RÉFÉRENCES DE PROFIL/REQUÊTE
# ──────────────────────────────────────────────

def _resolve_reference(ref_type: str, config: dict, raw_id: int):
    """Retourne (objet, catégorie) — catégorie identifie la section du bundle à remplir."""
    if ref_type == "db_profile":
        from core.sql_db import get_profile_object
        db_type = config.get("db_type", "ORACLE")
        obj = get_profile_object(db_type, raw_id)
        return obj, ("oracle" if db_type == "ORACLE" else "database")
    if ref_type == "ftp_profile":
        return db.get_ftp_profile(raw_id), "ftp"
    if ref_type == "smtp_profile":
        return db.get_smtp_profile(raw_id), "smtp"
    if ref_type == "sql_query":
        return db.get_sql_query(raw_id), "sql_query"
    return None, None


# ──────────────────────────────────────────────
#  SÉRIALISATION PAR ENTITÉ
# ──────────────────────────────────────────────

def _serialize_oracle_profile(p, fernet) -> dict:
    d = {
        "uuid": p.uuid, "name": p.name, "host": p.host, "port": p.port,
        "service_name": p.service_name, "sid": p.sid, "username": p.username,
        "auth_mode": p.auth_mode,
    }
    d.update(_serialize_password(p.password, fernet))
    return d


def _serialize_ftp_profile(p, fernet) -> dict:
    d = {
        "uuid": p.uuid, "name": p.name, "host": p.host, "port": p.port,
        "username": p.username,
        "protocol": str(p.protocol).replace("FtpProtocol.", ""),
    }
    d.update(_serialize_password(p.password, fernet))
    return d


def _serialize_smtp_profile(p, fernet) -> dict:
    d = {
        "uuid": p.uuid, "name": p.name, "host": p.host, "port": p.port,
        "username": p.username, "use_tls": p.use_tls, "from_address": p.from_address,
    }
    d.update(_serialize_password(p.password, fernet))
    return d


def _serialize_database_profile(p, fernet) -> dict:
    d = {
        "uuid": p.uuid, "name": p.name,
        "db_type": str(p.db_type).replace("DbType.", ""),
        "host": p.host, "port": p.port, "username": p.username,
        "database_name": p.database_name, "extra_json": p.extra_json,
    }
    d.update(_serialize_password(p.password, fernet))
    return d


def _serialize_sql_query(q) -> dict:
    return {
        "uuid": q.uuid, "name": q.name,
        "sql_text": q.sql_text, "description": q.description,
    }


_SERIALIZERS = {
    "oracle":   _serialize_oracle_profile,
    "ftp":      _serialize_ftp_profile,
    "smtp":     _serialize_smtp_profile,
    "database": _serialize_database_profile,
}


# ──────────────────────────────────────────────
#  EXPORT
# ──────────────────────────────────────────────

def export_pipeline(pipeline_id: int, password: str | None = None) -> ExportResult:
    try:
        pipeline = db.get_pipeline(pipeline_id)
        if not pipeline:
            return ExportResult(success=False, error=f"Pipeline ID {pipeline_id} introuvable.")

        steps = db.get_steps(pipeline_id)
        warnings: list[str] = []

        fernet = None
        kdf_meta = None
        if password:
            fernet, kdf_meta = _new_export_cipher(password)

        # needed[catégorie][id_local] = objet résolu — dédupliqué par id, un profil référencé par
        # plusieurs étapes n'est sérialisé qu'une fois.
        needed = {"oracle": {}, "ftp": {}, "smtp": {}, "database": {}, "sql_query": {}}
        exported_steps = []

        for step in steps:
            step_type = str(step.step_type).replace("StepType.", "")
            config = json.loads(step.config_json or "{}")
            exported_config = dict(config)

            for key, ref_type in _STEP_REFERENCES.get(step_type, []):
                raw_id = config.get(key)
                if raw_id is None:
                    continue
                obj, category = _resolve_reference(ref_type, config, raw_id)
                uuid_key = _UUID_KEY_FOR[key]
                exported_config.pop(key, None)
                if obj is not None:
                    exported_config[uuid_key] = obj.uuid
                    needed[category][raw_id] = obj
                else:
                    exported_config[uuid_key] = None
                    label = step.label or step_type
                    warnings.append(
                        f"Étape {step.step_order + 1} ({label}) : référence '{key}'={raw_id} "
                        "introuvable — non incluse dans l'export."
                    )

            exported_steps.append({
                "step_order":  step.step_order,
                "step_type":   step_type,
                "label":       step.label,
                "config":      exported_config,
                "retry_count": step.retry_count,
                "run_always":  step.run_always,
            })

        profiles_bundle = {
            category: [_SERIALIZERS[category](obj, fernet) for obj in objs.values()]
            for category, objs in needed.items() if category != "sql_query"
        }
        sql_queries_bundle = [_serialize_sql_query(q) for q in needed["sql_query"].values()]

        bundle = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "app_version":    __version__,
            "exported_at":    datetime.now(timezone.utc).isoformat(),
            "kind":           "pipeline",
            "pipeline": {
                "uuid":            pipeline.uuid,
                "name":            pipeline.name,
                "description":     pipeline.description,
                "frequency":       str(pipeline.frequency).replace("CronFrequency.", ""),
                "cron_expression": pipeline.cron_expression,
                "scheduled_time":  pipeline.scheduled_time,
                "scheduled_day":   pipeline.scheduled_day,
                "prevent_overlap": pipeline.prevent_overlap,
                "steps":           exported_steps,
            },
            "profiles":    profiles_bundle,
            "sql_queries": sql_queries_bundle,
        }
        if kdf_meta:
            bundle["kdf"] = kdf_meta

        return ExportResult(success=True, bundle=bundle, warnings=warnings)

    except Exception as e:
        return ExportResult(success=False, error=str(e))


def export_pipeline_to_file(pipeline_id: int, path, password: str | None = None) -> ExportResult:
    result = export_pipeline(pipeline_id, password)
    if result.success:
        Path(path).write_text(
            json.dumps(result.bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result
