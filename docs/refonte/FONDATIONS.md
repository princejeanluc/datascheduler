# Fondations communes

Ce que tous les écrans partagent. Le lot 0 (voir `LOTS.md`) met ces fondations en place. Les lots d'écran ne font ensuite que les utiliser.

## 1. Couleurs

Les maquettes reprennent la palette de `ui/styles.py::COLORS`. Pour chaque valeur hexadécimale lue dans le HTML d'une maquette, utilise la clé correspondante.

| Valeur dans la maquette | Clé `COLORS` | Usage |
|---|---|---|
| `#141210` | `bg_main` | fond de page |
| `#1c1a17` | `bg_panel` | panneaux, cartes de section, barre de navigation |
| `#242220` | `bg_card` | cartes intérieures, champs, pastilles |
| `#2c2925` | `bg_hover` | survol, séparateurs fins entre lignes |
| `#3d1f00` | `bg_active` | élément actif ou sélectionné |
| `#35322d` | `border` | bordures |
| `#FF7900` | `accent` | marque et action principale uniquement |
| `#ff9933` | `accent_pale` | liens, survol de l'accent |
| `#6BB4CF` | `signal_pale` | information, élément en cours, recherche |
| `#3fb950` | `success` | réussite |
| `#E8B339` | `warning` | avertissement, port d'erreur |
| `#f85149` | `danger` | échec, suppression |
| `#f2efeb` | `text_main` | texte principal |
| `#9c968d` | `text_dim` | texte secondaire |
| `#756f66` | `text_muted` | texte discret, graduations |

### Clés à ajouter (lot 0)

Les maquettes utilisent quelques valeurs qui n'ont pas encore de clé. Ajoute-les à `COLORS` sans modifier les clés existantes.

| Nouvelle clé | Valeur | Usage |
|---|---|---|
| `border_strong` | `#4a463f` | bordure de bulle, de fenêtre flottante, zone pointillée |
| `text_soft` | `#c9c4bc` | texte courant dans un bandeau coloré |
| `success_dim` | `#2f7d3c` | case « 1 réussite » de la carte de fréquence |
| `bg_info` / `border_info` | `#16282f` / `#24414b` | bandeau d'information |
| `bg_success` / `border_success` | `#132116` / `#24502c` | bandeau de réussite |
| `bg_warning` / `border_warning` | `#241d10` / `#5a4719` | bandeau d'avertissement |
| `bg_danger` / `border_danger` | `#2a1715` / `#6e2b28` | bandeau d'échec |

Les trois couleurs des graphiques de Ressources (`#3987e5`, `#199e70`, `#d95926`) existent déjà dans `resources_view.py`. Elles restent réservées aux séries de données.

### Couleur des étapes : par famille, plus par type

Aujourd'hui, chacun des 18 types d'étape a sa propre couleur (`ui/step_editor/common.py::STEP_META[...]["color"]`). La maquette Grammaire (validée) remplace ces 18 couleurs par 7 familles : « la couleur dit la famille, le texte dit le moteur ».

| Famille | Couleur | Types |
|---|---|---|
| Extraction et chargement | `#6BB4CF` | DB_EXTRACT, FTP_DOWNLOAD, DB_LOAD |
| Transfert et diffusion | `#b5c96a` | FTP_UPLOAD, LOCAL_COPY, COMPRESS |
| Exécution et scripts | `#d68fb8` | DB_EXECUTE, PYTHON_SCRIPT |
| Big Data | `#4fb3a0` | SPARK_SQL, SQOOP_EXPORT, SQOOP_IMPORT |
| Notification | `#c9a37a` | EMAIL_NOTIFY, HTTP_REQUEST |
| Variables | `#b8b2a8` | EXTRACT_VARIABLES, SET_VARIABLE |
| Passerelles | `#a58cf0` | CONDITION, GATEWAY_PARALLEL, GATEWAY_JOIN (forme losange, pas rectangle) |

Impact à couvrir dans la note du lot 0 :

- `STEP_META["color"]` est lu par `node_item.py`, `pipelines_view.py`, `widgets.py` (vignettes) et `step_type_chooser_dialog.py`. Ajoute une clé `family` à `STEP_META` et fais dériver `color` de la famille. Les appelants n'ont alors rien à changer.
- La famille « Big Data » n'existe pas dans `_CATEGORY_ORDER` : Spark SQL et Sqoop sont rangés dans « Exécution & scripts ». La famille de couleur et la section du sélecteur sont deux choses distinctes. Ne change pas les sections du sélecteur dans le lot 0.
- La couleur n'est pas écrite dans les exports `.dspipeline` (`database/export_import.py` ne la mentionne pas) : le format d'export n'est pas touché.

## 2. Typographie

Polices déjà embarquées : IBM Plex Sans (interface) et JetBrains Mono (données, heures, chiffres, code). Utilise `FONT_UI_STACK` et `FONT_MONO_STACK`.

Tailles relevées dans les maquettes :

| Usage | Taille | Graisse | Police |
|---|---|---|---|
| Titre de page | 26 px | 600 | Plex Sans |
| Surtitre de page (en majuscules) | 11 px, espacement 0,08em | 400 | Mono, `text_dim` |
| Titre de section ou de panneau | 17 px | 600 | Plex Sans |
| Libellé de ligne | 14 px | 600 | Plex Sans |
| Texte courant, boutons, champs | 13 px | 400 / 600 | Plex Sans |
| Description sous un libellé | 12,5 px | 400 | Plex Sans, `text_dim` |
| Pastille, légende | 10,5 à 11 px | 600 | Plex Sans |
| Valeur de carte de chiffres | 22 px | 600 | Mono |

Ajoute les paliers manquants à `FONT_SIZES` (`page_title: 26`, `panel_title: 17`, `row_label: 14`). Les valeurs existantes ne changent pas.

## 3. Composants partagés

À créer dans un module unique, par exemple `ui/components/`. Chaque composant prend ses couleurs dans `COLORS`.

| Composant | Ce qu'il fait | Existe déjà | Utilisé par |
|---|---|---|---|
| En-tête de page | surtitre en Mono, titre, sous-titre, zone d'actions à droite | `_make_title`, `_make_subtitle` (à étendre) | tous |
| Bouton principal | fond `accent`, texte noir, 34 px de haut | non | tous |
| Bouton secondaire | bordure `border`, transparent | non | tous |
| Bouton discret | 30 px, bordure, texte et icône facultative | non (`_action_btn` est un bouton carré à icône seule, à garder pour les tableaux) | panneaux, bandeaux |
| Pastille de statut | point de couleur + mot (réussi, échec, en cours) ; jamais la couleur seule | `_make_status_badge` | Aujourd'hui, Pipelines, Historique, Ressources |
| Pastille d'information | texte 10,5 px dans un contour arrondi | non | Paramètres, Connexions |
| Bandeau | info, réussite, avertissement, échec ; icône, titre, texte, actions | non | Paramètres, Ressources, Pipelines, Connexions |
| Panneau latéral | glisse depuis la droite (560 px par défaut), ombre, se ferme par Échap | non | Historique, Connexions, Aujourd'hui |
| Fenêtre modale | titre, contenu, pied avec actions | `DIALOG_STYLE` (à reprendre) | Pipelines, Connexions, SQL |
| Bulle | ancrée à un élément, avec une flèche | non | Historique (jour de la carte) |
| Carte de chiffres | libellé, valeur en Mono, précision | `StatCard` | Aujourd'hui, Ressources |
| Ligne de réglage | libellé, description, contrôle à droite, pastille de prise d'effet | `SettingsView._add_row` | Paramètres |
| Interrupteur | 38 × 22 px, `accent` quand activé | non | Paramètres |
| Sélecteur de plage | boutons arrondis 1h / 6h / 24h / 7j | `ResourcesView._set_active_range` | Ressources, Historique |
| Champ de recherche | icône loupe, raccourci affiché | `_make_search_input` | tous |
| État vide | icône, titre, texte, action | `_make_empty_label` (à étendre) | Pipelines, Ressources |

Règle : un composant existant est étendu en gardant sa signature. On ne le remplace pas.

## 4. Heures affichées

La base stocke les instants en UTC naïf (`datetime.utcnow`). `Pipeline.next_run_at` fait exception : il est stocké naïf dans le fuseau `AppSettings.timezone`.

À créer dans le lot 0, par exemple `ui/time_display.py` :

- `to_display(dt_utc)` convertit un instant UTC naïf vers le fuseau réglé et renvoie un datetime naïf prêt à formater ;
- `fmt_time(dt_utc)`, `fmt_datetime(dt_utc)`, `fmt_relative(dt_utc)` (« il y a 4 min ») ;
- une variante pour `next_run_at`, qui ne convertit pas.

Le fuseau est relu à chaque appel, ou mis en cache et invalidé par l'enregistrement des Paramètres. Puis chaque écran remplace ses `strftime` directs par ces fonctions : `grep -rn strftime ui/` en donne 17 aujourd'hui. Ajoute un test qui vérifie qu'un run lancé à 05:00 UTC s'affiche 07:00 avec `Europe/Paris` en été.

## 5. Captures de contrôle

Pour comparer une vue à sa maquette sans affichage :

```python
import os; os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.fonts import register_app_fonts
app = QApplication([]); register_app_fonts()
view = SettingsView(); view.resize(1440 - 56, 900); view.show(); app.processEvents()
view.grab().save("docs/refonte/captures/parametres.png")
```

Un script `scripts/capture_views.py` qui produit une capture par vue et par état fait partie du lot 0. Il sert ensuite à toutes les PR.

## 6. Clés de couleur supplémentaires relevées dans les fiches

| Nouvelle clé | Valeur | Usage |
|---|---|---|
| `bg_section` | `#191714` | fond d'un en-tête de section dans une liste |
| `token_bg` / `token_border` | `#2a1d10` / `#4a3520` | jeton `{…}` dans l'éditeur SQL |
| `sql_string` | `#7ec8a4` | chaîne dans l'éditeur SQL (déjà utilisée dans `ui/sql_editor.py`) |
| `editor_current_line` | `#1f1c18` | ligne courante de l'éditeur |
| `relation` | `#a58cf0` | lien vers un objet lié (« via Bastion », « après X ») ; même valeur que la famille Passerelles |
