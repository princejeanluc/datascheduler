"""
DataScheduler — core/steps/ftp_upload.py
Étape : upload du fichier de contexte vers un serveur FTP/FTPS/SFTP.
"""

from .base import BaseStep, StepContext, StepResult


class FtpUploadStep(BaseStep):
    REQUIRES = {"output_file"}

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            from database import db_manager as db
            from core.ftp import FtpUploader, config_from_profile

            ftp_id      = self.config.get("ftp_profile_id")
            ftp_profile = db.get_ftp_profile(ftp_id)

            if not ftp_profile:
                result.error = f"Profil FTP ID {ftp_id} introuvable."
                return result

            if not ctx.output_file or not ctx.output_file.exists():
                result.error = "Aucun fichier source disponible dans le contexte."
                return result

            path_tpl = self.config.get("remote_path_tpl", "/export/").rstrip("/") + "/"
            file_tpl = self.config.get("filename_tpl", "export_{yyyyMMdd}.csv")
            remote   = ctx.resolve_tokens(path_tpl + file_tpl)

            ctx.log(f"Upload FTP : {ftp_profile.host} → {remote}")
            if on_progress:
                on_progress("Upload FTP…", 80)

            ftp_cfg       = config_from_profile(ftp_profile)
            uploader      = FtpUploader(ftp_cfg)
            upload_result = uploader.upload(ctx.output_file, remote)

            if not upload_result.success:
                result.error = f"Upload FTP : {upload_result.error}"
                return result

            ctx.extra["remote_path"] = upload_result.remote_path
            ctx.log(
                f"Upload FTP : OK — {upload_result.bytes_sent / 1024:.1f} Ko "
                f"en {upload_result.duration_s:.1f}s"
            )
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
