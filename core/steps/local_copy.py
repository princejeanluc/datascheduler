"""
DataScheduler — core/steps/local_copy.py
Étape : copie locale du fichier de contexte avec résolution de tokens datetime.
"""

import shutil
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


class LocalCopyStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            if not ctx.output_file or not ctx.output_file.exists():
                result.error = "Aucun fichier source disponible dans le contexte."
                return result

            dest_dir_tpl = self.config.get("dest_dir", "")
            file_tpl     = self.config.get("filename_tpl", "")

            if not dest_dir_tpl:
                result.error = "Dossier de destination non configuré."
                return result

            dest_dir  = Path(ctx.resolve_tokens(dest_dir_tpl))
            dest_dir.mkdir(parents=True, exist_ok=True)

            filename  = ctx.resolve_tokens(file_tpl) if file_tpl else ctx.output_file.name
            dest_path = dest_dir / filename

            if on_progress:
                on_progress(f"Copie locale → {dest_path.name}", 85)

            shutil.copy2(ctx.output_file, dest_path)
            ctx.extra["local_path"] = str(dest_path)
            ctx.log(f"Copie locale : OK → {dest_path}")
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
