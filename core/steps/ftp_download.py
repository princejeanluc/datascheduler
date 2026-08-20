"""
DataScheduler — core/steps/ftp_download.py
Étape : téléchargement d'un fichier distant (FTP/FTPS/SFTP) vers un fichier
temporaire — utilisable comme source (première étape) d'un pipeline.
"""

import tempfile
from pathlib import Path

from .base import BaseStep, StepContext, StepResult


class FtpDownloadStep(BaseStep):
    PRODUCES = {"output_file"}

    def run(self, ctx: StepContext, cancel_event=None, on_progress=None) -> StepResult:
        result = StepResult()
        tmp_path: Path | None = None

        try:
            from database import db_manager as db
            from core.ftp import FtpUploader, config_from_profile

            ftp_id      = self.config.get("ftp_profile_id")
            ftp_profile = db.get_ftp_profile(ftp_id)

            if not ftp_profile:
                result.error = f"Profil FTP ID {ftp_id} introuvable."
                return result

            remote_tpl = self.config.get("remote_path_tpl", "")
            if not remote_tpl:
                result.error = "Chemin distant non configuré."
                return result

            remote = ctx.resolve_tokens(remote_tpl)

            suffix = Path(remote).suffix or ".dat"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, prefix="ds_")
            tmp_path = Path(tmp.name)
            tmp.close()

            ctx.log(f"Download {ftp_profile.protocol} : {ftp_profile.host} → {remote}")
            if on_progress:
                on_progress("Téléchargement…", 30)

            ftp_cfg  = config_from_profile(ftp_profile)
            uploader = FtpUploader(ftp_cfg)
            dl_result = uploader.download(remote, tmp_path)

            if not dl_result.success:
                result.error = f"Download : {dl_result.error}"
                return result

            ctx.output_file = tmp_path
            ctx.log(
                f"Download : OK — {dl_result.bytes_received / 1024:.1f} Ko "
                f"en {dl_result.duration_s:.1f}s"
            )
            result.success = True

        except Exception as e:
            result.error = str(e)
        finally:
            # Le fichier temporaire est créé avant de savoir si le téléchargement va réussir ;
            # s'il échoue (résultat en échec ou exception), il ne sera jamais référencé dans
            # ctx.artifacts donc jamais nettoyé par run_pipeline — à nettoyer ici.
            if tmp_path is not None and not result.success and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return result
