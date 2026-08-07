"""
DataScheduler — core/steps/compress.py
Étape : compression du fichier de contexte (ou d'une source explicite/nommée) en archive ZIP —
utile pour réduire la taille d'un fichier avant diffusion (email, FTP), notamment quand un
serveur mail d'entreprise limite la taille des pièces jointes.

Source à 3 niveaux, même patron que LOCAL_COPY/DB_LOAD/FTP_UPLOAD dès la conception (pas de
retrofit à faire plus tard) : chemin explicite prioritaire, sinon Source ciblée explicitement
(reads_from_step_key, résolu génériquement par core/pipeline.py avant l'appel à run()), sinon
ctx.output_file (étape précédente, comportement par défaut).
"""

import tempfile
import zipfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


class CompressStep(BaseStep):
    REQUIRES = {"output_file"}
    PRODUCES = {"output_file"}

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()
        zip_path: Path | None = None

        try:
            # Chemin explicite (facultatif) : prioritaire sur ctx.output_file — permet à cette
            # étape d'être autonome (« juste compresser ce fichier »), sans maillon amont fictif.
            explicit_path = (self.config.get("explicit_path") or "").strip()
            source_path = Path(ctx.resolve_tokens(explicit_path)) if explicit_path else ctx.output_file
            if not source_path or not source_path.exists():
                result.error = "Aucun fichier source disponible (ni chemin explicite, ni contexte)."
                return result

            archive_name_tpl = (self.config.get("archive_name_tpl") or "").strip()
            archive_name = ctx.resolve_tokens(archive_name_tpl) if archive_name_tpl else f"{source_path.stem}.zip"
            if not archive_name.lower().endswith(".zip"):
                archive_name += ".zip"

            # Répertoire temporaire dédié (plutôt qu'un tempfile.NamedTemporaryFile classique,
            # au nom généré illisible) pour que l'archive produite porte un nom exploitable sur
            # le disque — visible tel quel comme nom de pièce jointe par EMAIL_NOTIFY en aval, ou
            # comme nom de fichier distant par FTP_UPLOAD. Le fichier lui-même est nettoyé en fin
            # de pipeline comme tout autre artefact (core/pipeline.py) ; seul le répertoire, vide
            # une fois le fichier supprimé, peut subsister jusqu'au nettoyage périodique du
            # dossier temporaire du système — compromis accepté, ce n'est jamais qu'un dossier
            # vide, pas une fuite de données.
            tmp_dir = Path(tempfile.mkdtemp(prefix="ds_zip_"))
            zip_path = tmp_dir / archive_name

            if on_progress:
                on_progress(f"Compression de {source_path.name}…", 60)

            size_before = source_path.stat().st_size
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(source_path, arcname=source_path.name)
            size_after = zip_path.stat().st_size

            ratio = (1 - size_after / size_before) * 100 if size_before else 0.0
            ctx.log(
                f"Compression : OK — {source_path.name} "
                f"({size_before / 1024:.0f} Ko → {size_after / 1024:.0f} Ko, -{ratio:.0f}%)"
            )

            ctx.output_file = zip_path
            output_name = self.config.get("output_name")
            if output_name:
                ctx.artifacts[output_name] = zip_path

            result.success = True

        except Exception as e:
            result.error = str(e)
        finally:
            if zip_path is not None and not result.success and zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass

        return result
