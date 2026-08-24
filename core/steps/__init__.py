from .base           import StepContext, StepResult, BaseStep
from .ftp_upload     import FtpUploadStep
from .local_copy     import LocalCopyStep
from .python_script  import PythonScriptStep
from .ftp_download   import FtpDownloadStep
from .email_notify   import EmailNotifyStep
from .http_request   import HttpRequestStep
from .db_extract     import DbExtractStep
from .db_execute     import DbExecuteStep
from .db_load        import DbLoadStep
from .condition      import ConditionStep
from .spark_sql      import SparkSqlStep
from .compress       import CompressStep
from .sqoop_export   import SqoopExportStep
from .gateway_parallel import GatewayParallelStep
from .gateway_join   import GatewayJoinStep

_REGISTRY: dict[str, type[BaseStep]] = {
    "FTP_UPLOAD":     FtpUploadStep,
    "LOCAL_COPY":     LocalCopyStep,
    "PYTHON_SCRIPT":  PythonScriptStep,
    "FTP_DOWNLOAD":   FtpDownloadStep,
    "EMAIL_NOTIFY":   EmailNotifyStep,
    "HTTP_REQUEST":   HttpRequestStep,
    "DB_EXTRACT":     DbExtractStep,
    "DB_EXECUTE":     DbExecuteStep,
    "DB_LOAD":        DbLoadStep,
    "CONDITION":      ConditionStep,
    "SPARK_SQL":      SparkSqlStep,
    "COMPRESS":       CompressStep,
    "SQOOP_EXPORT":   SqoopExportStep,
    "GATEWAY_PARALLEL": GatewayParallelStep,
    "GATEWAY_JOIN":      GatewayJoinStep,
}


def known_step_types() -> set[str]:
    """Types d'étape reconnus par cette version de l'application — utilisé par l'import de
    pipeline (database/export_import.py) pour détecter un bundle référençant un type d'étape
    introduit par une version plus récente, avant de tenter de le recréer en base."""
    return set(_REGISTRY)


def get_step(step_type: str, config: dict) -> BaseStep:
    cls = _REGISTRY.get(step_type)
    if cls is None:
        raise ValueError(f"Type d'étape inconnu : {step_type!r}")
    return cls(config)


def get_step_requirements(step_type: str) -> tuple[set[str], set[str]]:
    """Retourne (REQUIRES, PRODUCES) pour un type d'étape, sans l'instancier."""
    cls = _REGISTRY.get(step_type)
    if cls is None:
        return set(), set()
    return set(cls.REQUIRES), set(cls.PRODUCES)


def step_produces_output_file(step_type: str, config: dict) -> bool:
    """
    Est-ce que CETTE instance de step (config comprise) produit potentiellement un fichier dans
    ctx.output_file — au-delà du PRODUCES statique de la classe, qui ne peut pas exprimer une
    production conditionnelle à la config (ex: SPARK_SQL, qui ne produit que si la case
    "Récupérer le résultat" est cochée). Utilisé par le sélecteur "Source" de l'éditeur, avant
    toute exécution — l'exécution elle-même (core/pipeline.py) n'en a pas besoin puisqu'elle
    observe directement si ctx.output_file a changé après coup.
    """
    _, produces = get_step_requirements(step_type)
    if "output_file" in produces:
        return True
    if step_type == "SPARK_SQL":
        return bool((config or {}).get("fetch_result"))
    if step_type == "GATEWAY_JOIN":
        # Ne produit que si l'utilisateur a explicitement désigné la branche dont l'artefact
        # continue (chantier Gateway) — sinon la jonction ne fait QUE synchroniser, aucune
        # donnée à proposer comme "Source" pour une étape plus en aval.
        return bool((config or {}).get("artifact_source_step_key"))
    return False


def get_step_output_ports(step_type: str) -> tuple[str, ...]:
    """Retourne les ports de sortie nommés d'un type d'étape (chantier 6a) — un seul port
    implicite ("output_file") pour tous les steps existants ; plusieurs pour un nœud comme
    ConditionStep ("true", "false"). Un port "error" est TOUJOURS ajouté en plus, pour tous les
    types (chantier port d'erreur générique, analogue BPMN "événement-frontière d'erreur") —
    seul point d'ancrage, jamais déclaré par chaque classe individuellement (BaseStep.
    OUTPUT_PORTS ne liste que les ports "normaux/succès"), pour qu'un futur type d'étape en
    hérite automatiquement sans y penser."""
    cls = _REGISTRY.get(step_type)
    base = cls.OUTPUT_PORTS if cls is not None else ("output_file",)
    return base + ("error",)


def is_routing_node(step_type: str) -> bool:
    """Un nœud de routage/jonction (aujourd'hui CONDITION, GATEWAY_PARALLEL, GATEWAY_JOIN) se
    rend en losange sur le canevas plutôt qu'en rectangle — voir ui/graph_editor/node_item.py.
    Faux pour tout type inconnu, même défaut que la classe de base."""
    cls = _REGISTRY.get(step_type)
    return bool(cls is not None and cls.IS_ROUTING_NODE)


def preserves_output(step_type: str) -> bool:
    """Le fichier produit par ce type d'étape est une destination PERMANENTE (ex: LOCAL_COPY),
    pas un scratch intermédiaire — le nettoyage des fichiers temporaires en fin de
    run_pipeline() (core/pipeline.py) doit l'exclure de sa suppression. Faux pour tout type
    inconnu, même défaut que la classe de base."""
    cls = _REGISTRY.get(step_type)
    return bool(cls is not None and cls.PRESERVES_OUTPUT)


def get_join_mode(step_type: str, config: dict) -> str | None:
    """Mode de jonction ("AND"/"OR") d'un step passerelle-jonction (chantier Gateway) — None
    pour tout autre type (jamais un littéral "GATEWAY_JOIN" codé en dur dans core/pipeline.py,
    même indirection que is_routing_node()). "OR" par défaut si la config ne précise rien —
    repli sûr correspondant au comportement historique déjà en place pour tout nœud
    multi-prédécesseurs (should_skip dans core/pipeline.py)."""
    cls = _REGISTRY.get(step_type)
    if cls is None or not cls.IS_JOIN_GATEWAY:
        return None
    return (config or {}).get("join_mode") or "OR"
