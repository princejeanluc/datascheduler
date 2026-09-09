"""
DataScheduler — core/sqoop.py
Exécution de `sqoop export`/`sqoop import` (Hive/HCatalog ↔ Oracle) sur un cluster Hadoop via un
nœud edge — miroir de core/spark.py pour la mécanique SSH/kinit (voir core/hadoop_edge.py,
chantier K, extrait de core/spark.py précisément pour être partagé ici sans dupliquer la logique
kinit par pseudo-terminal).

Portée volontairement limitée à Oracle (le besoin exprimé est spécifiquement `jdbc:oracle:thin`)
— pas de généralisation spéculative à d'autres moteurs non demandés. `sqoop import` (le sens
inverse) a été ajouté après coup, sur demande explicite — _run_sqoop() porte toute la mécanique
SSH/kinit/élévation commune aux deux sens, seule la commande construite diffère
(build_sqoop_export_command/build_sqoop_import_command).
"""

import shlex
import time
import uuid as _uuid_module
from dataclasses import dataclass

from core.hadoop_edge import (
    SshExecConfig, KerberosConfig, ElevationConfig,
    _connect, _close_all, _kinit, read_remote_file, run_command_with_elevation, watch_cancel,
)
from core.sql_db import SqlDbConfig


@dataclass
class SqoopCommandResult:
    """Résultat générique d'une commande sqoop (export ou import) — nom volontairement neutre
    depuis l'ajout de sqoop import (anciennement SqoopExportResult, quand seul l'export existait)."""
    success: bool
    error: str = ""
    duration_s: float = 0.0


def build_oracle_jdbc_url(cfg: SqlDbConfig) -> str:
    """
    jdbc:oracle:thin:@(DESCRIPTION=...) — le format TNS complet attendu par le driver JDBC
    Oracle utilisé par Sqoop (un outil Java, donc pas le DSN python-oracledb de core/sql_db.py,
    un format distinct). SERVICE_NAME si renseigné sur le profil, sinon SID.
    """
    conn_data = f"SERVICE_NAME={cfg.service_name}" if cfg.service_name else f"SID={cfg.sid}"
    return (
        f"jdbc:oracle:thin:@(DESCRIPTION=(ADDRESS_LIST=(ADDRESS=(PROTOCOL=TCP)"
        f"(HOST={cfg.host})(PORT={cfg.port})))(CONNECT_DATA=({conn_data})))"
    )


def build_sqoop_export_command(connect_url: str, username: str, password: str,
                                hcatalog_database: str, hcatalog_table: str, oracle_table: str,
                                sqoop_conf: str, masked: bool = False) -> str:
    """
    Construit la commande `sqoop export`. `masked=True` remplace le mot de passe par `****` —
    utilisé exclusivement pour la journalisation (ctx.log()/PipelineRun.log_text), jamais pour
    l'exécution réelle : le mot de passe Oracle ne doit JAMAIS apparaître en clair dans les logs
    persistés. Chaque valeur passe par shlex.quote() (absent de l'exemple d'origine mais
    nécessaire dès qu'un mot de passe/nom de table arrive dans une commande shell distante).
    """
    pw = "****" if masked else password
    parts = [
        "sqoop export -jt local",
        f"--connect {shlex.quote(connect_url)}",
        f"--username {shlex.quote(username)}",
        f"--password {shlex.quote(pw)}",
        f"--hcatalog-table {shlex.quote(hcatalog_table)}",
        f"--hcatalog-database {shlex.quote(hcatalog_database)}",
        f"--table {shlex.quote(oracle_table)}",
    ]
    cmd = " ".join(parts)
    if sqoop_conf:
        cmd = f"{cmd} {sqoop_conf}"
    return cmd


def build_sqoop_import_command(connect_url: str, username: str, password: str, oracle_table: str,
                                hcatalog_database: str, hcatalog_table: str, num_mappers: int,
                                split_by_column: str, sqoop_conf: str, masked: bool = False) -> str:
    """
    Construit la commande `sqoop import` — sens inverse de build_sqoop_export_command() : table
    Oracle SOURCE, HCatalog/Hive CIBLE. Suppose la table HCatalog cible déjà créée, même choix
    que DB_LOAD pour les tables SQL (pas de génération de DDL / --create-hcatalog-table).

    `num_mappers` (`-m`) contrôle la parallélisation de la LECTURE côté Oracle — un souci que
    `sqoop export` n'a jamais, puisqu'il écrit dans Oracle sans avoir à en partitionner la
    lecture. `1` (défaut appelant) fonctionne sans configuration supplémentaire quelle que soit
    la table ; au-delà, Sqoop exige `--split-by` pour savoir comment répartir les lignes entre
    mappers — la validation (mappers > 1 sans split_by_column) est faite par l'appelant
    (SqoopImportStep), cette fonction se contente de construire la commande telle que fournie.
    """
    pw = "****" if masked else password
    parts = [
        "sqoop import -jt local",
        f"--connect {shlex.quote(connect_url)}",
        f"--username {shlex.quote(username)}",
        f"--password {shlex.quote(pw)}",
        f"--table {shlex.quote(oracle_table)}",
        f"--hcatalog-database {shlex.quote(hcatalog_database)}",
        f"--hcatalog-table {shlex.quote(hcatalog_table)}",
        f"-m {int(num_mappers)}",
    ]
    if int(num_mappers) > 1:
        parts.append(f"--split-by {shlex.quote(split_by_column)}")
    cmd = " ".join(parts)
    if sqoop_conf:
        cmd = f"{cmd} {sqoop_conf}"
    return cmd


def _run_sqoop(ssh_cfg: SshExecConfig, krb_cfg: KerberosConfig | None, real_cmd: str, verb: str,
               timeout: int = 3600, elevation_cfg: ElevationConfig | None = None,
               on_progress=None, cancel_event=None) -> SqoopCommandResult:
    """
    Exécution SSH d'une commande sqoop déjà construite — partagée par run_sqoop_export()/
    run_sqoop_import(), qui ne diffèrent que par la commande elle-même (`real_cmd`) et son verbe
    ("export"/"import", pour des messages de progression/erreur cohérents avec la commande
    réellement lancée). Deux chemins distincts, choisis selon `elevation_cfg` :

    - **Sans élévation** (chemin historique, inchangé) : SSH → kinit optionnel (`krb_cfg` peut
      être `None` — certaines équipes n'utilisent pas Kerberos pour Sqoop) → exécute la commande
      non-interactivement, sortie redirigée vers des fichiers distants et bornée par `timeout`
      → sur échec, lit le fichier d'erreur distant → nettoie les fichiers temporaires distants
      (best-effort) → ferme toujours la connexion SSH.
    - **Avec élévation** (`sudo su <target_user>`, ex : compte technique partagé "nifi") :
      délègue entièrement à `core.hadoop_edge.run_command_with_elevation()`, qui enchaîne
      élévation + kinit optionnel + la commande réelle sur UN SEUL canal shell interactif —
      nécessaire car un `sudo su` réussi ne survit jamais à un `exec_command()` séparé (voir
      docstring de ce module dans core/hadoop_edge.py). `krb_cfg`, s'il est fourni, s'applique
      alors APRÈS l'élévation (l'utilisateur cible peut avoir sa propre identité Kerberos).

    `on_progress(msg, pct)`, si fourni, reflète la phase bloquante en cours (connexion, kinit,
    export/import) — chemin élévation transmis tel quel à run_command_with_elevation(), qui a
    déjà ses propres phases (chantier O).
    """
    start = time.monotonic()

    if elevation_cfg:
        try:
            ok, output = run_command_with_elevation(
                ssh_cfg, real_cmd, timeout, elevation_cfg=elevation_cfg, krb_cfg=krb_cfg,
                on_progress=on_progress, cancel_event=cancel_event,
            )
            if not ok:
                return SqoopCommandResult(
                    success=False, error=f"sqoop {verb} a échoué : {output}",
                    duration_s=time.monotonic() - start,
                )
            return SqoopCommandResult(success=True, duration_s=time.monotonic() - start)
        except Exception as e:
            return SqoopCommandResult(success=False, error=str(e), duration_s=time.monotonic() - start)

    client = None
    token = _uuid_module.uuid4().hex
    remote_out = f"/tmp/ds_sqoop_{token}.out"
    remote_err = f"/tmp/ds_sqoop_{token}.err"

    try:
        if on_progress:
            on_progress("Connexion au nœud edge…", 10)
        client = _connect(ssh_cfg)

        if krb_cfg:
            if on_progress:
                on_progress("Authentification Kerberos…", 25)
            ok, message = _kinit(client, krb_cfg, cancel_event=cancel_event)
            if not ok:
                return SqoopCommandResult(
                    success=False, error=f"Authentification Kerberos : {message}",
                    duration_s=time.monotonic() - start,
                )

        full_cmd = f"timeout {int(timeout)}s {real_cmd} > {remote_out} 2>{remote_err}"

        if on_progress:
            on_progress(f"{verb.capitalize()} Sqoop en cours…", 40)
        _stdin, stdout, _stderr = client.exec_command(full_cmd, timeout=timeout + 30)
        with watch_cancel(stdout.channel, cancel_event):
            exit_status = stdout.channel.recv_exit_status()

        if cancel_event is not None and cancel_event.is_set():
            return SqoopCommandResult(success=False, error="Annulé par l'utilisateur.",
                                      duration_s=time.monotonic() - start)

        if exit_status != 0:
            err_text = read_remote_file(client, remote_err)
            return SqoopCommandResult(
                success=False, error=f"sqoop {verb} a échoué (code {exit_status}) : {err_text}",
                duration_s=time.monotonic() - start,
            )

        return SqoopCommandResult(success=True, duration_s=time.monotonic() - start)

    except Exception as e:
        return SqoopCommandResult(success=False, error=str(e), duration_s=time.monotonic() - start)
    finally:
        if client is not None:
            try:
                client.exec_command(f"rm -f {remote_out} {remote_err}")
            except Exception:
                pass
            _close_all(client)


def run_sqoop_export(ssh_cfg: SshExecConfig, krb_cfg: KerberosConfig | None, oracle_cfg: SqlDbConfig,
                      hcatalog_database: str, hcatalog_table: str, oracle_table: str,
                      sqoop_conf: str, timeout: int = 3600,
                      elevation_cfg: ElevationConfig | None = None, on_progress=None,
                      cancel_event=None) -> SqoopCommandResult:
    """Construit la commande `sqoop export` (Hive/HCatalog → Oracle) puis délègue à _run_sqoop()
    pour toute la mécanique SSH/kinit/élévation — voir sa docstring pour le détail des deux
    chemins d'exécution possibles."""
    real_cmd = build_sqoop_export_command(
        build_oracle_jdbc_url(oracle_cfg), oracle_cfg.username, oracle_cfg.password,
        hcatalog_database, hcatalog_table, oracle_table, sqoop_conf, masked=False,
    )
    return _run_sqoop(ssh_cfg, krb_cfg, real_cmd, "export", timeout=timeout,
                       elevation_cfg=elevation_cfg, on_progress=on_progress, cancel_event=cancel_event)


def run_sqoop_import(ssh_cfg: SshExecConfig, krb_cfg: KerberosConfig | None, oracle_cfg: SqlDbConfig,
                      oracle_table: str, hcatalog_database: str, hcatalog_table: str,
                      num_mappers: int, split_by_column: str, sqoop_conf: str, timeout: int = 3600,
                      elevation_cfg: ElevationConfig | None = None, on_progress=None,
                      cancel_event=None) -> SqoopCommandResult:
    """Construit la commande `sqoop import` (Oracle → Hive/HCatalog, sens inverse de
    run_sqoop_export()) puis délègue à _run_sqoop() — même mécanique SSH/kinit/élévation,
    aucune duplication."""
    real_cmd = build_sqoop_import_command(
        build_oracle_jdbc_url(oracle_cfg), oracle_cfg.username, oracle_cfg.password,
        oracle_table, hcatalog_database, hcatalog_table, num_mappers, split_by_column, sqoop_conf,
        masked=False,
    )
    return _run_sqoop(ssh_cfg, krb_cfg, real_cmd, "import", timeout=timeout,
                       elevation_cfg=elevation_cfg, on_progress=on_progress, cancel_event=cancel_event)
