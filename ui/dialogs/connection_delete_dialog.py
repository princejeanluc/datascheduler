"""
DataScheduler — ui/dialogs/connection_delete_dialog.py
Confirmation de suppression d'un profil de connexion (refonte, lot A-Connexions, A11) — remplace
le `QMessageBox.question` inline de `ConnectionsView._confirm_delete`. Même patron que
`ui/dialogs/pipeline_delete_dialog.py` (lot A-Pipelines) : surtitre SUPPRIMER en danger, titre,
encadré listant les pipelines concernés, « Annuler »/« Supprimer quand même ». Pas de
« Remplacer puis supprimer » (C9, gated — pastille « proposé » sur la maquette
Connexions-suppression.html).
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from ui.styles import COLORS, DIALOG_STYLE


class ConnectionDeleteDialog(QDialog):
    """`profile_kind` : libellé du type (« Oracle », « FTP », « SSH », « d'élévation »... — même
    texte que l'ancien message de `_confirm_delete`). `used_by` : noms de pipelines qui
    utilisent ce profil. `bastion_users` : pour un profil SSH, noms des autres profils SSH qui
    l'utilisent comme bastion (reparti en connexion directe si la suppression est confirmée) —
    `None` pour tout autre type."""

    def __init__(self, parent, profile_kind: str, profile_name: str, used_by: list,
                 bastion_users: list | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Supprimer {profile_name}")
        self.setMinimumWidth(480)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui(profile_kind, profile_name, used_by, bastion_users or [])

    def _build_ui(self, profile_kind: str, profile_name: str, used_by: list, bastion_users: list):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        surtitle = QLabel("SUPPRIMER")
        surtitle.setStyleSheet(
            f"color: {COLORS['danger']}; font-size: 10px; font-weight: 700; letter-spacing: 0.06em;"
        )
        root.addWidget(surtitle)

        title = QLabel(f"Supprimer {profile_name} ?")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['text_main']};")
        root.addWidget(title)

        if used_by:
            n = len(used_by)
            intro = QLabel(
                f"{n} pipeline{'s' if n > 1 else ''} se sert{'vent' if n > 1 else ''} de ce "
                f"profil {profile_kind}. Le(s) supprimer quand même ? Ces pipelines échoueront à "
                f"leur prochaine exécution :"
            )
            intro.setWordWrap(True)
            intro.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 12.5px;")
            root.addWidget(intro)

            used_frame = QFrame()
            used_frame.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_main']}; border: 1px solid {COLORS['border']}; "
                f"border-radius: 8px; }}"
            )
            used_layout = QVBoxLayout(used_frame)
            used_layout.setContentsMargins(12, 10, 12, 10)
            used_layout.setSpacing(6)
            for name in used_by:
                lbl = QLabel(f"<b>{name}</b>")
                lbl.setStyleSheet(
                    f"color: {COLORS['text_main']}; font-size: 12.5px; background: transparent; "
                    f"border: none;"
                )
                used_layout.addWidget(lbl)
            root.addWidget(used_frame)
        else:
            intro = QLabel(f"Supprimer ce profil {profile_kind} ?")
            intro.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 12.5px;")
            root.addWidget(intro)

        if bastion_users:
            n = len(bastion_users)
            names = ", ".join(bastion_users)
            bastion_note = QLabel(
                f"Utilisé comme bastion par {n} profil{'s' if n > 1 else ''} SSH : {names} "
                f"(ils repasseront en connexion directe)."
            )
            bastion_note.setWordWrap(True)
            bastion_note.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11.5px;")
            root.addWidget(bastion_note)

        root.addWidget(self._sep())
        btn_row = QHBoxLayout(); btn_row.setSpacing(8); btn_row.addStretch()
        btn_cancel = QPushButton("Annuler"); btn_cancel.setObjectName("secondary")
        btn_cancel.setFixedHeight(36); btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        self.btn_delete = QPushButton("Supprimer quand même"); self.btn_delete.setObjectName("danger")
        self.btn_delete.setFixedHeight(36); self.btn_delete.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_delete)
        root.addLayout(btn_row)

    def _sep(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        return f
