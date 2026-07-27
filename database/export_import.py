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

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import crypto, db_manager as db
from .models import DbType, FtpProtocol
from version import __version__

CURRENT_SCHEMA_VERSION = 2   # v2 (chantier 6a/6b) : ajoute "edges" + pos_x/pos_y par étape — un
                             # bundle v1 s'importe toujours normalement (edges/positions par défaut)
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


@dataclass
class EntityDecision:
    category:    str                 # "oracle" | "ftp" | "smtp" | "database" | "sql_query"
    uuid:        str
    action:      str                 # "reuse" | "create"
    existing_id: int | None = None
    data:        dict | None = None  # entrée brute du bundle, si action == "create"


@dataclass
class ImportPlan:
    success: bool
    bundle:  dict | None = None
    pipeline_action:      str | None = None   # "create" | "collision"
    pipeline_existing_id: int | None = None
    profile_decisions:    list = field(default_factory=list)    # list[EntityDecision]
    sql_query_decisions:  list = field(default_factory=list)    # list[EntityDecision]
    fernet:   object | None = None    # Fernet dérivé une fois, réutilisé par apply_import
    warnings: list = field(default_factory=list)
    error:    str | None = None
    needs_password: bool = False


@dataclass
class ApplyResult:
    success: bool
    pipeline_id: int | None = None
    warnings: list = field(default_factory=list)
    error: str | None = None


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


def _category_for_ref(ref_type: str, config: dict) -> str | None:
    """Symétrique de _resolve_reference, côté import : détermine la catégorie sans rien lire en base."""
    if ref_type == "db_profile":
        return "oracle" if config.get("db_type", "ORACLE") == "ORACLE" else "database"
    if ref_type == "ftp_profile":
        return "ftp"
    if ref_type == "smtp_profile":
        return "smtp"
    if ref_type == "sql_query":
        return "sql_query"
    return None


_GETTER_BY_CATEGORY = {
    "oracle":   db.get_oracle_profile_by_uuid,
    "ftp":      db.get_ftp_profile_by_uuid,
    "smtp":     db.get_smtp_profile_by_uuid,
    "database": db.get_database_profile_by_uuid,
}


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
                "pos_x":       step.pos_x,
                "pos_y":       step.pos_y,
            })

        # Arêtes du graphe (chantier 6a) — référencent des _step_key, déjà présents tels quels
        # dans le config de chaque étape ci-dessus (aucune traduction UUID nécessaire, ce ne sont
        # pas des références de profil/requête). Liste vide pour un pipeline jamais ouvert dans
        # l'éditeur graphique — se comporte alors exactement comme un bundle v1.
        edges = db.get_edges(pipeline_id)
        exported_edges = [
            {
                "from_step_key": e.from_step_key,
                "from_port":     e.from_port,
                "to_step_key":   e.to_step_key,
                "to_port":       e.to_port,
            }
            for e in edges
        ]

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
                "edges":           exported_edges,
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


# ──────────────────────────────────────────────
#  IMPORT (chantier 5b core) — sans écran de revue : règles par défaut sûres,
#  jamais d'écrasement silencieux. Voir docs/ARCHITECTURE.md / mémoire projet.
# ──────────────────────────────────────────────

def _unique_name(base: str, taken: set) -> str:
    """Désambiguïsation en mémoire — aucune requête DB par tentative."""
    if base not in taken:
        return base
    i = 2
    while f"{base} ({i})" in taken:
        i += 1
    return f"{base} ({i})"


def _decrypt_bundle_password(entry: dict, fernet: Fernet | None) -> str:
    if entry.get("password_status") == "encrypted" and fernet is not None:
        return fernet.decrypt(entry["encrypted_password"].encode("utf-8")).decode("utf-8")
    return ""


def _verify_password(bundle: dict, fernet: Fernet) -> None:
    """Lève InvalidToken si le mot de passe est incorrect — teste le premier secret trouvé."""
    for entries in bundle.get("profiles", {}).values():
        for entry in entries:
            if entry.get("password_status") == "encrypted":
                fernet.decrypt(entry["encrypted_password"].encode("utf-8"))
                return


def _create_profile_from_bundle(category: str, data: dict, fernet: Fernet | None,
                                 taken_names: dict) -> int:
    password = _decrypt_bundle_password(data, fernet)
    name = _unique_name(data["name"], taken_names[category])
    taken_names[category].add(name)

    if category == "oracle":
        obj = db.create_oracle_profile(
            name=name, host=data["host"], port=data["port"], username=data["username"],
            password=password, service_name=data.get("service_name"), sid=data.get("sid"),
            auth_mode=data.get("auth_mode", "DEFAULT"), uuid=data["uuid"],
        )
    elif category == "ftp":
        obj = db.create_ftp_profile(
            name=name, host=data["host"], port=data["port"], username=data["username"],
            password=password, protocol=data.get("protocol", "FTP"), uuid=data["uuid"],
        )
    elif category == "smtp":
        obj = db.create_smtp_profile(
            name=name, host=data["host"], port=data["port"], from_address=data["from_address"],
            username=data.get("username"), password=password,
            use_tls=data.get("use_tls", True), uuid=data["uuid"],
        )
    elif category == "database":
        obj = db.create_database_profile(
            name=name, db_type=data["db_type"], host=data["host"], port=data["port"],
            username=data["username"], password=password,
            database_name=data.get("database_name"),
            extra=json.loads(data.get("extra_json") or "{}"),
            uuid=data["uuid"],
        )
    else:
        raise ValueError(f"Catégorie de profil inconnue : {category!r}")
    return obj.id


def _create_sql_query_from_bundle(data: dict, taken_names: dict) -> int:
    name = _unique_name(data["name"], taken_names["sql_query"])
    taken_names["sql_query"].add(name)
    obj = db.create_sql_query(
        name=name, sql_text=data["sql_text"], description=data.get("description"),
        uuid=data["uuid"],
    )
    return obj.id


def plan_import(bundle: dict, password: str | None = None) -> ImportPlan:
    try:
        schema_version = bundle.get("schema_version")
        if schema_version is None:
            return ImportPlan(success=False, error="Fichier invalide : schema_version manquant.")
        if schema_version > CURRENT_SCHEMA_VERSION:
            return ImportPlan(success=False, error=(
                f"Ce fichier a été exporté avec une version plus récente du format "
                f"(v{schema_version}, seule la v{CURRENT_SCHEMA_VERSION} est supportée par cette "
                "version de l'application) — mettez à jour DataScheduler avant de l'importer."
            ))
        # schema_version < CURRENT_SCHEMA_VERSION : c'est ici que la chaîne de transcripteurs
        # s'appliquerait — aujourd'hui no-op, une seule version du format existe.

        fernet = None
        kdf_meta = bundle.get("kdf")
        if kdf_meta:
            if not password:
                return ImportPlan(
                    success=False, needs_password=True,
                    error="Ce fichier contient des identifiants chiffrés — mot de passe requis.",
                )
            try:
                salt = base64.b64decode(kdf_meta["salt"])
                key = _derive_key(password, salt)
                fernet = Fernet(key)
                _verify_password(bundle, fernet)
            except InvalidToken:
                return ImportPlan(success=False, error="Mot de passe incorrect.")

        profile_decisions: list[EntityDecision] = []
        for category, entries in bundle.get("profiles", {}).items():
            getter = _GETTER_BY_CATEGORY.get(category)
            if getter is None:
                continue
            for entry in entries:
                existing = getter(entry["uuid"])
                if existing:
                    profile_decisions.append(
                        EntityDecision(category, entry["uuid"], "reuse", existing.id))
                else:
                    profile_decisions.append(
                        EntityDecision(category, entry["uuid"], "create", data=entry))

        sql_query_decisions: list[EntityDecision] = []
        for entry in bundle.get("sql_queries", []):
            existing = db.get_sql_query_by_uuid(entry["uuid"])
            if existing:
                sql_query_decisions.append(
                    EntityDecision("sql_query", entry["uuid"], "reuse", existing.id))
            else:
                sql_query_decisions.append(
                    EntityDecision("sql_query", entry["uuid"], "create", data=entry))

        pipeline_uuid = bundle["pipeline"]["uuid"]
        existing_pipeline = db.get_pipeline_by_uuid(pipeline_uuid)
        pipeline_action = "collision" if existing_pipeline else "create"
        pipeline_existing_id = existing_pipeline.id if existing_pipeline else None

        return ImportPlan(
            success=True, bundle=bundle,
            pipeline_action=pipeline_action, pipeline_existing_id=pipeline_existing_id,
            profile_decisions=profile_decisions, sql_query_decisions=sql_query_decisions,
            fernet=fernet,
        )

    except Exception as e:
        return ImportPlan(success=False, error=str(e))


def plan_import_from_file(path, password: str | None = None) -> ImportPlan:
    try:
        bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return ImportPlan(success=False, error=f"Fichier illisible : {e}")
    return plan_import(bundle, password)


def apply_import(plan: ImportPlan) -> ApplyResult:
    if not plan.success or plan.bundle is None:
        return ApplyResult(success=False, error=plan.error or "Plan d'import invalide.")
    try:
        taken_names = {
            "oracle":    {p.name for p in db.get_oracle_profiles()},
            "ftp":       {p.name for p in db.get_ftp_profiles()},
            "smtp":      {p.name for p in db.get_smtp_profiles()},
            "database":  {p.name for p in db.get_database_profiles()},
            "sql_query": {q.name for q in db.get_sql_queries()},
            "pipeline":  {p.name for p in db.get_pipelines()},
        }

        # (catégorie, uuid) -> id local — construite au fil des décisions "reuse"/"create".
        uuid_to_local_id: dict = {}

        for decision in plan.profile_decisions:
            if decision.action == "reuse":
                uuid_to_local_id[(decision.category, decision.uuid)] = decision.existing_id
            else:
                local_id = _create_profile_from_bundle(
                    decision.category, decision.data, plan.fernet, taken_names)
                uuid_to_local_id[(decision.category, decision.uuid)] = local_id

        for decision in plan.sql_query_decisions:
            if decision.action == "reuse":
                uuid_to_local_id[("sql_query", decision.uuid)] = decision.existing_id
            else:
                local_id = _create_sql_query_from_bundle(decision.data, taken_names)
                uuid_to_local_id[("sql_query", decision.uuid)] = local_id

        pipeline_data = plan.bundle["pipeline"]
        translated_steps = []
        for step in pipeline_data["steps"]:
            step_type = step["step_type"]
            config = dict(step["config"])
            for key, ref_type in _STEP_REFERENCES.get(step_type, []):
                uuid_key = _UUID_KEY_FOR[key]
                ref_uuid = config.pop(uuid_key, None)
                if ref_uuid is None:
                    continue
                category = _category_for_ref(ref_type, config)
                local_id = uuid_to_local_id.get((category, ref_uuid))
                if local_id is not None:
                    config[key] = local_id
            translated_steps.append({
                "step_type":   step_type,
                "label":       step.get("label"),
                "config":      config,
                "retry_count": step.get("retry_count", 0),
                "run_always":  step.get("run_always", False),
                "pos_x":       step.get("pos_x", 0),
                "pos_y":       step.get("pos_y", 0),
            })

        # Arêtes du graphe (chantier 6a) — référencent des _step_key déjà présents tels quels
        # dans translated_steps ci-dessus (voir export_pipeline()) : aucune traduction à faire,
        # elles voyagent verbatim. Liste vide pour un bundle v1 ou un pipeline sans graphe.
        translated_edges = list(pipeline_data.get("edges", []))

        if plan.pipeline_action == "overwrite" and plan.pipeline_existing_id:
            # Choix explicite de l'écran de revue (chantier 5c) — remplace le pipeline local
            # existant en place (même id/UUID, c'est justement pour ça qu'il y avait collision).
            db.update_pipeline(
                plan.pipeline_existing_id,
                name=pipeline_data["name"],
                description=pipeline_data.get("description"),
                frequency=pipeline_data.get("frequency", "DAILY"),
                cron_expression=pipeline_data.get("cron_expression"),
                scheduled_time=pipeline_data.get("scheduled_time"),
                scheduled_day=pipeline_data.get("scheduled_day"),
                prevent_overlap=pipeline_data.get("prevent_overlap", False),
            )
            db.save_pipeline_graph(plan.pipeline_existing_id, translated_steps, translated_edges)
            new_pipeline_id = plan.pipeline_existing_id
        else:
            if plan.pipeline_action == "create":
                name = _unique_name(pipeline_data["name"], taken_names["pipeline"])
                pipeline_uuid = pipeline_data["uuid"]
            else:
                # "collision" non résolu (pas passé par l'écran de revue) ou "rename" (choix
                # explicite) : jamais d'écrasement silencieux — copie renommée, nouvel UUID généré.
                name = _unique_name(f"{pipeline_data['name']} (import)", taken_names["pipeline"])
                pipeline_uuid = None

            new_pipeline = db.create_pipeline(
                name=name,
                description=pipeline_data.get("description"),
                frequency=pipeline_data.get("frequency", "DAILY"),
                cron_expression=pipeline_data.get("cron_expression"),
                scheduled_time=pipeline_data.get("scheduled_time"),
                scheduled_day=pipeline_data.get("scheduled_day"),
                prevent_overlap=pipeline_data.get("prevent_overlap", False),
                uuid=pipeline_uuid,
            )
            db.save_pipeline_graph(new_pipeline.id, translated_steps, translated_edges)
            new_pipeline_id = new_pipeline.id

        return ApplyResult(success=True, pipeline_id=new_pipeline_id, warnings=list(plan.warnings))

    except Exception as e:
        return ApplyResult(success=False, error=str(e))
