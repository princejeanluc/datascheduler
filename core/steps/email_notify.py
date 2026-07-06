"""
DataScheduler — core/steps/email_notify.py
Étape : envoi d'un email de notification (avec pièce jointe optionnelle).
"""

from .base import BaseStep, StepContext, StepResult


class EmailNotifyStep(BaseStep):

    def run(self, ctx: StepContext, on_progress=None) -> StepResult:
        result = StepResult()

        try:
            from database import db_manager as db
            from core.email import EmailSender, config_from_profile

            smtp_id = self.config.get("smtp_profile_id")
            smtp_profile = db.get_smtp_profile(smtp_id)

            if not smtp_profile:
                result.error = f"Profil SMTP ID {smtp_id} introuvable."
                return result

            to_raw = self.config.get("to", "")
            to = [a.strip() for a in ctx.resolve_tokens(to_raw).split(",") if a.strip()]
            if not to:
                result.error = "Aucun destinataire configuré."
                return result

            subject = ctx.resolve_tokens(self.config.get("subject_tpl", ""))
            body    = ctx.resolve_tokens(self.config.get("body_tpl", ""))
            attach_output = self.config.get("attach_output_file", False)

            attachment = None
            if attach_output:
                if ctx.output_file and ctx.output_file.exists():
                    attachment = ctx.output_file
                else:
                    ctx.log("Avertissement : pièce jointe demandée mais aucun fichier disponible.")

            ctx.log(f"Envoi email : {smtp_profile.host} → {', '.join(to)}")
            if on_progress:
                on_progress("Envoi email…", 80)

            smtp_cfg = config_from_profile(smtp_profile)
            sender   = EmailSender(smtp_cfg)
            send_result = sender.send(to=to, subject=subject, body=body, attachment=attachment)

            if not send_result.success:
                result.error = f"Envoi email : {send_result.error}"
                return result

            ctx.log(f"Envoi email : OK en {send_result.duration_s:.1f}s")
            result.success = True

        except Exception as e:
            result.error = str(e)

        return result
