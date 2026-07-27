"""
DataScheduler — core/steps/local_copy.py
Étape : copie locale du fichier de contexte avec résolution de tokens datetime.
"""

import shutil
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


class LocalCopyStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            # Chemin explicite (facultatif) : prioritaire sur ctx.output_file — permet à cette
            # étape d'être autonome (« juste copier ce fichier »), sans maillon amont fictif.
            explicit_path = (self.config.get("explicit_path") or "").strip()
            source_path = Path(ctx.resolve_tokens(explicit_path)) if explicit_path else ctx.output_file
            if not source_path or not source_path.exists():
                result.error = "Aucun fichier source disponible (ni chemin explicite, ni contexte)."
                return result

            dest_dir_tpl = self.config.get("dest_dir", "")
            file_tpl     = self.config.get("filename_tpl", "")

            if not dest_dir_tpl:
                result.error = "Dossier de destination non configuré."
                return result

            dest_dir  = Path(ctx.resolve_tokens(dest_dir_tpl))
            dest_dir.mkdir(parents=True, exist_ok=True)

            filename  = ctx.resolve_tokens(file_tpl) if file_tpl else source_path.name
            dest_path = dest_dir / filename

            if on_progress:
                on_progress(f"Copie locale → {dest_path.name}", 85)

            shutil.copy2(source_path, dest_path)
            ctx.extra["local_path"] = str(dest_path)
            ctx.log(f"Copie locale : OK → {dest_path}")
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
