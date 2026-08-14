"""
DataScheduler — ui/styles.py
Palette de couleurs et styles CSS partagés entre tous les widgets.
"""

COLORS = {
    # Fonds — noir chaud réel (léger biais orange dans chaque canal), plutôt que le gris neutre
    # (R=G=B) précédent qui contredisait le commentaire d'origine (audit d'identité, 2026-08).
    "bg_main":    "#141210",   # fond principal
    "bg_panel":   "#1c1a17",   # panneaux latéraux / nav
    "bg_card":    "#242220",   # cartes et zones de formulaire
    "bg_hover":   "#2c2925",   # survol nav
    "bg_active":  "#3d1f00",   # item actif nav — teinte orange sombre

    # Bordures
    "border":     "#35322d",   # séparateurs neutres, même biais chaud

    # Accent Orange (charte Orange SA — #FF7900)
    "accent":     "#FF7900",   # orange primaire — marque + action primaire uniquement
    "accent_dim": "#cc6200",   # orange foncé (pressed / focus)
    "accent_pale":"#ff9933",   # orange clair (hover)

    # Second accent "signal" — bleu-cyan sourd, usage structurel/informationnel (jamais la marque
    # ni l'action primaire). Introduit pour désengorger l'orange, qui portait jusqu'ici trois sens
    # simultanés (marque, action, statut "en cours") — audit d'identité, 2026-08.
    "signal":      "#3E8FB0",
    "signal_dim":  "#285d70",
    "signal_pale": "#6BB4CF",

    # Sémantique
    "success":    "#3fb950",   # vert succès
    # Ambre doré, délibérément distinct de "accent" (#FF7900) — l'ancienne valeur (identique à
    # l'accent) faisait qu'un avertissement était visuellement indissociable d'un bouton actif ou
    # d'un survol (audit de design, 2026-08). Reste dans la même famille chaude que la charte
    # (hue ~45° contre ~29° pour l'accent) sans se confondre avec lui.
    "warning":    "#E8B339",
    "danger":     "#f85149",   # rouge erreur

    # Textes — même correction de biais chaud que les fonds
    "text_main":  "#f2efeb",   # texte principal — blanc doux
    "text_dim":   "#9c968d",   # texte secondaire
    "text_muted": "#756f66",   # texte discret / version (contraste AA sur bg_main)
}

# ──────────────────────────────────────────────
#  TYPOGRAPHIE — IBM Plex Sans (interface) / JetBrains Mono (données tabulaires, logs, code).
#  Polices embarquées via ui/fonts.py (voir register_app_fonts(), appelée au démarrage). Chaque
#  usage QSS garde une chaîne de repli complète : si l'enregistrement échoue pour une raison
#  quelconque, Qt retombe silencieusement sur Segoe UI / Consolas, jamais de rendu cassé.
# ──────────────────────────────────────────────

FONT_UI = "IBM Plex Sans"
FONT_MONO = "JetBrains Mono"
FONT_UI_STACK = f'"{FONT_UI}", "Segoe UI", "Helvetica Neue", sans-serif'
FONT_MONO_STACK = f'"{FONT_MONO}", "Consolas", monospace'

# ──────────────────────────────────────────────
#  ÉCHELLE TYPOGRAPHIQUE — les 6 paliers déjà utilisés de fait dans toute l'application (audit de
#  design, 2026-08), déclarés ici comme référence pour toute nouvelle vue. Les usages existants ne
#  sont pas encore migrés vers ces constantes (chaque écran continue d'écrire "font-size: 13px"
#  en dur) — cette déclaration fixe l'échelle sans risquer de régression sur l'existant ; une
#  migration progressive peut s'appuyer dessus au fil des prochains écrans touchés.
# ──────────────────────────────────────────────

FONT_SIZES = {
    "display":         28,   # valeur de StatCard (Dashboard)
    "title":           20,   # titre de section (#section_title)
    "subtitle_dialog": 15,   # titre de dialogue de configuration d'étape
    "body":            13,   # texte courant, boutons, champs — taille de base globale
    "label":           11,   # libellé de carte en majuscules (StatCard, badges)
    "caption":         10,   # version, notes de bas de champ, texte le plus discret
}

DIALOG_STYLE = f"""
QDialog {{
    background-color: {COLORS['bg_panel']};
    color: {COLORS['text_main']};
    font-family: {FONT_UI_STACK};
    font-size: 13px;
}}
QLabel {{
    background: transparent;
    border: none;
    color: {COLORS['text_main']};
}}
QPushButton {{
    background-color: {COLORS['accent']};
    color: #000000;
    border: none;
    border-radius: 4px;
    padding: 7px 16px;
    font-weight: 700;
    font-size: 13px;
}}
QPushButton:hover   {{ background-color: {COLORS['accent_pale']}; }}
QPushButton:pressed {{ background-color: {COLORS['accent_dim']}; color: white; }}
QPushButton#secondary {{
    background-color: transparent;
    color: {COLORS['text_main']};
    border: 1px solid {COLORS['border']};
}}
QPushButton#secondary:hover {{
    background-color: {COLORS['bg_hover']};
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
}}
QPushButton#danger {{
    background-color: transparent;
    color: {COLORS['danger']};
    border: 1px solid {COLORS['danger']};
}}
QPushButton#danger:hover {{
    background-color: {COLORS['danger']};
    color: white;
}}
QLineEdit, QSpinBox, QComboBox {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 6px 10px;
    color: {COLORS['text_main']};
    font-size: 13px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 2px solid {COLORS['accent']};
}}
QComboBox::drop-down {{ border: none; padding-right: 8px; }}
QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['bg_active']};
    color: {COLORS['text_main']};
}}
QFrame#card {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
}}
QScrollBar:vertical {{
    background: {COLORS['bg_panel']};
    width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 3px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {COLORS['accent']}; }}
"""