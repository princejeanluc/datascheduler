"""
DataScheduler — ui/main_window/pipeline_actions.py
Logique d'exécution manuelle d'un pipeline, factorisée hors de `PipelinesView._on_run_pipeline`
(lot A-Atelier-main, A8) pour être partagée avec le bouton « Exécuter » de l'en-tête de l'Atelier
(`atelier_pipelines_view.py`) — même chemin que depuis la liste : vérification de recouvrement,
validation à blanc rapide (sans test de connexion), lancement local ou distant.
"""

from PySide6.QtWidgets import QMessageBox, QWidget


def run_pipeline_now(parent: QWidget, pipeline_id: int) -> None:
    """Ex-corps de `PipelinesView._on_run_pipeline` — l'appelant reste responsable de son propre
    rafraîchissement après l'appel (`PipelinesView.refresh()`, inutile côté Atelier dont le
    canevas s'actualise déjà par polling)."""
    from database import db_manager as db
    from ui.dialogs import RunProgressDialog
    from core.pipeline import is_pipeline_running, request_cancel
    from core.execution_mode import (
        is_background_mode_active, is_pipeline_running_anywhere,
        request_run_now, request_cancel_run,
    )
    p = db.get_pipeline(pipeline_id)
    if not p:
        return

    background = is_background_mode_active()
    currently_running = (
        is_pipeline_running_anywhere(pipeline_id) if background
        else is_pipeline_running(pipeline_id)
    )

    if p.prevent_overlap and currently_running:
        box = QMessageBox(parent)
        box.setWindowTitle("Pipeline déjà en cours")
        box.setText(
            f"« {p.name} » est déjà en cours d'exécution.\n\n"
            "L'interruption est coopérative : elle prend effet à la fin de l'étape en "
            "cours, pas instantanément si celle-ci est longue (ex: une extraction Oracle "
            "de plusieurs minutes). Relancez manuellement une fois le run arrêté."
        )
        btn_interrupt = box.addButton("Interrompre l'exécution en cours", QMessageBox.DestructiveRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() == btn_interrupt:
            if not request_cancel_run(pipeline_id):
                request_cancel(pipeline_id)
            QMessageBox.information(
                parent, "Demande envoyée",
                "L'arrêt a été demandé — le statut affichera « Arrêt en cours » jusqu'à ce "
                "que l'étape en cours se termine."
            )
        return

    # Validation structurelle avant tout lancement — nœuds orphelins, ports requis non connectés,
    # cycles, références de profil disparues. test_connections=False : jamais de test réseau réel
    # ici, cette phase reste rapide et synchrone.
    from core.pipeline import dry_run_pipeline
    dry_run = dry_run_pipeline(pipeline_id, test_connections=False)
    if dry_run.errors:
        QMessageBox.warning(
            parent, "Pipeline invalide",
            f"« {p.name} » ne peut pas s'exécuter tel quel :\n\n"
            + "\n".join(f"• {e}" for e in dry_run.errors),
        )
        return
    if dry_run.warnings:
        reply = QMessageBox.question(
            parent, "Avertissement",
            f"« {p.name} » pourrait tourner sans les données attendues :\n\n"
            + "\n".join(f"• {w}" for w in dry_run.warnings)
            + "\n\nContinuer quand même ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

    if request_run_now(pipeline_id):
        from .remote_run_dialog import open_remote_run_dialog
        open_remote_run_dialog(parent, pipeline_id, p.name)
    else:
        RunProgressDialog(pipeline_id, p.name, parent).exec()
