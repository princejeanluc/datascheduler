"""
DataScheduler — core/spark.py
Exécution de requêtes Spark SQL sur un cluster Hadoop via un nœud edge : connexion SSH,
authentification Kerberos (kinit), exécution non-interactive de spark-sql, rapatriement
optionnel du résultat par SFTP.

La mécanique SSH/kinit elle-même vit dans core/hadoop_edge.py (chantier K — extraite pour être
partagée avec SQOOP_EXPORT, qui tourne sur le même cluster Kerberisé) ; ce module ré-exporte les
noms historiquement importés d'ici par le reste du code (core/pipeline.py, core/steps/spark_sql.py,
ui/dialogs/{connection_health_dialog,kerberos_profile_dialog,ssh_profile_dialog}.py) pour que le
refactor soit invisible pour ces appelants — aucun changement de comportement.
"""

import time
import uuid as _uuid_module
from dataclasses import dataclass
from pathlib import Path

from core.hadoop_edge import (  # noqa: F401 — ré-export, voir docstring ci-dessus
    SshExecConfig, KerberosConfig, ConnectionTestResult,
    config_from_profile, kerberos_config_from_profile,
    _connect, _close_all, _kinit, test_ssh_connection, test_kerberos_auth,
    read_remote_file as _read_remote_file,
)


@dataclass
class SparkSqlResult:
    success: bool
    error: str = ""
    local_output_path: Path | None = None
    duration_s: float = 0.0


# ──────────────────────────────────────────────
#  EXÉCUTION SPARK SQL
# ──────────────────────────────────────────────

def run_spark_sql(ssh_cfg: SshExecConfig, krb_cfg: KerberosConfig, spark_conf: str, query: str,
                   fetch_result: bool, local_output_path: Path | None = None,
                   timeout: int = 3600, on_progress=None) -> SparkSqlResult:
    """
    SSH → kinit → dépose la requête dans un fichier .sql temporaire distant (SFTP — évite tout
    problème d'échappement shell d'une requête inline) → exécute spark-sql non-interactivement,
    sortie redirigée vers un fichier distant, borné par `timeout` (le utilitaire shell, pas
    seulement le paramètre côté client — exec_command() ne borne pas la durée du process
    distant lui-même) → si fetch_result, rapatrie ce fichier par SFTP → nettoie les fichiers
    temporaires distants (best-effort, jamais bloquant) → ferme toujours la connexion SSH
    (finally), même principe que le try/finally déjà appliqué aux steps DB_EXTRACT/DB_EXECUTE/
    DB_LOAD (core/steps/*.py).

    `on_progress(msg, pct)`, si fourni, est appelé à chaque changement de phase (connexion,
    kinit, envoi de la requête, exécution, récupération) — le point important est le tick juste
    avant `exec_command()` : c'est l'attente potentiellement la plus longue (la requête tourne
    réellement sur le cluster), auparavant indiscernable d'un kinit bloqué puisque aucun tick
    n'était émis entre le début et la toute fin de cette fonction (chantier O).
    """
    start = time.monotonic()
    client = None
    token = _uuid_module.uuid4().hex
    remote_sql = f"/tmp/ds_spark_{token}.sql"
    remote_out = f"/tmp/ds_spark_{token}.out"
    remote_err = f"/tmp/ds_spark_{token}.err"

    try:
        if on_progress:
            on_progress("Connexion au nœud edge…", 5)
        client = _connect(ssh_cfg)

        if on_progress:
            on_progress("Authentification Kerberos…", 15)
        ok, message = _kinit(client, krb_cfg)
        if not ok:
            return SparkSqlResult(
                success=False, error=f"Authentification Kerberos : {message}",
                duration_s=time.monotonic() - start,
            )

        if on_progress:
            on_progress("Envoi de la requête…", 30)
        sftp = client.open_sftp()
        try:
            with sftp.open(remote_sql, "w") as f:
                f.write(query)
        finally:
            sftp.close()

        # Sans cette option, spark-sql omet l'en-tête de colonnes — un résultat récupéré comme
        # fichier doit en avoir un pour rester exploitable (ex: mise en forme CSV côté step,
        # étape LOCAL_COPY/DB_LOAD en aval). Injectée seulement si fetch_result et si l'appelant
        # n'a pas déjà sa propre valeur pour ce réglage dans sa config Spark libre.
        effective_conf = spark_conf
        if fetch_result and "spark.sql.cli.print.header" not in spark_conf:
            effective_conf = f"{spark_conf} --conf spark.sql.cli.print.header=true".strip()

        cmd = (
            f"timeout {int(timeout)}s spark-sql -S {effective_conf} "
            f"-f {remote_sql} > {remote_out} 2>{remote_err}"
        )
        if on_progress:
            on_progress("Exécution de la requête sur le cluster…", 40)
        _stdin, stdout, _stderr = client.exec_command(cmd, timeout=timeout + 30)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            err_text = _read_remote_file(client, remote_err)
            return SparkSqlResult(
                success=False, error=f"spark-sql a échoué (code {exit_status}) : {err_text}",
                duration_s=time.monotonic() - start,
            )

        if fetch_result and local_output_path is not None:
            if on_progress:
                on_progress("Récupération du résultat…", 85)
            sftp = client.open_sftp()
            try:
                sftp.get(remote_out, str(local_output_path))
            finally:
                sftp.close()

        return SparkSqlResult(
            success=True,
            local_output_path=local_output_path if fetch_result else None,
            duration_s=time.monotonic() - start,
        )

    except Exception as e:
        return SparkSqlResult(success=False, error=str(e), duration_s=time.monotonic() - start)
    finally:
        if client is not None:
            try:
                client.exec_command(f"rm -f {remote_sql} {remote_out} {remote_err}")
            except Exception:
                pass
            _close_all(client)
