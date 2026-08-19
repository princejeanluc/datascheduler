# Changelog

Tous les changements notables de DataScheduler sont documentés dans ce fichier.

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), numérotation selon
[SemVer](https://semver.org/lang/fr/) : `MAJOR.MINOR.PATCH`.

## Politique de version

- **PATCH** (`0.2.x`) — correctif de bug, sans nouvelle fonctionnalité ni changement de
  comportement visible (ex : un chevauchement visuel, une donnée mal résolue).
- **MINOR** (`0.x.0`) — nouvelle fonctionnalité rétrocompatible : nouveau type d'étape, nouvel
  écran, nouvelle option de configuration. Les pipelines et exports existants continuent de
  fonctionner sans modification.
- **MAJOR** (`x.0.0`) — changement de paradigme ou rupture de compatibilité : un format d'export
  qui ne se relit plus tel quel, une étape ou un profil supprimé, un changement du modèle
  d'exécution qui demande une action de l'utilisateur.

Ce fichier est mis à jour à chaque commit qui change un comportement visible par l'utilisateur
(nouvelle fonctionnalité, correctif, dépréciation) — pas pour du refactoring pur ou des tests.
Les entrées s'accumulent sous **[Non publié]** jusqu'à ce que `version.py` soit incrémentée ; à
ce moment la section est renommée avec le numéro et la date de version.

`CURRENT_SCHEMA_VERSION` (`database/export_import.py`) est un numéro **indépendant** de
`__version__` : il ne suit que la structure du bundle `.dspipeline` exporté (voir sa docstring),
pas l'ensemble des types d'étape/profil qu'il peut référencer à l'intérieur. Ce deuxième aspect
est couvert séparément par une vérification de compatibilité au moment de l'import (voir plus
bas pour son introduction).

## [Non publié]

## [0.29.1] - 2026-08-19

### Corrigé
- Éditeur graphique : le sélecteur "Source" et le bouton "+ Artefact" d'un champ d'étape
  n'affichaient jamais les étapes réellement connectées sur le canevas — toujours "étape
  précédente (par défaut)" sans nom, quel que soit le nombre d'arêtes entrantes dessinées à la
  main. `_on_add_step()`/`_on_node_double_clicked()` passaient `prior_steps=[]` en dur au
  dialogue de configuration d'étape, sans lien avec les arêtes de la scène — contrairement à
  l'éditeur linéaire, où cette liste a toujours été correctement remplie. Corrigé : à l'édition
  d'un nœud existant, la liste reflète désormais ses arêtes entrantes réelles ; à l'ajout d'un
  nouveau nœud (pas encore connecté), tous les nœuds déjà présents sur le canevas sont proposés,
  à connecter ensuite par glisser-déposer.

## [0.29.0] - 2026-08-18

### Ajouté
- Exécution en arrière-plan (worker + client léger) : nouveau mode "Avec exécution en
  arrière-plan" dans Paramètres, à côté du mode "Dans l'application seulement" (défaut,
  comportement inchangé). Une fois activé (redémarrage requis), un worker détaché
  (`DataScheduler.exe --worker`) est enregistré comme tâche planifiée Windows à l'ouverture de
  session (`schtasks`, droits utilisateur — pas d'élévation admin) et devient le seul exécuteur
  de pipelines, planifiés comme manuels : il continue de tourner après la fermeture de
  l'application et survit à une déconnexion/reconnexion. L'appli desktop devient un pur client
  dans ce mode — un lancement manuel ("Exécuter maintenant") ouvre un dialogue de suivi à
  distance qui relit la progression écrite en base par le worker, avec un bouton "Arrêter"
  (interruption coopérative relayée au worker).
- Nouvelle ligne "État du worker en arrière-plan" dans Paramètres (Ordonnanceur) — dérivée du
  dernier échantillon de ressources (déjà écrit en continu par le job d'échantillonnage), sans
  nouvelle mesure de vivacité.
- Repasser en "Dans l'application seulement" désinscrit la tâche planifiée et arrête
  immédiatement le worker déjà lancé (pas d'attente d'une prochaine déconnexion).

## [0.28.0] - 2026-08-17

### Ajouté
- Plafond d'exécutions simultanées **appliqué** — champ stocké depuis le chantier écran
  Paramètres mais jamais utilisé jusqu'ici : `run_pipeline()` refuse désormais tout nouveau
  lancement (manuel, planifié ou en chaîne) au-delà du plafond configuré, sans mettre en file
  d'attente (choix assumé — voir la description du champ dans Paramètres). Un run planifié
  refusé n'est pas rejoué automatiquement, il attend son prochain déclenchement normal.
- Nouvel écran "Ressources" (nav rail, entre Historique et Paramètres) : CPU/mémoire agrégés de
  l'application dans le temps (jamais une mesure par pipeline — ils tournent en threads dans le
  même process, impossible à attribuer proprement), mis en regard du nombre de pipelines en
  cours sur le même axe temporel. Survoler un point synchronise le curseur sur les 3 graphiques
  et liste précisément les pipelines actifs à cet instant — à l'utilisateur de faire le lien
  entre une pointe de ressources et une salve de pipelines, pas à l'appli de l'inventer.
  Sélecteur de plage (1h/6h/24h/7j). Nouvelle catégorie "Ressources" dans Paramètres (intervalle
  d'échantillonnage, rétention).

## [0.27.0] - 2026-08-15

### Ajouté
- Nouvel écran "Paramètres" (nav rail, entre Historique et Aide) réunissant tout ce qui était
  jusqu'ici câblé en dur dans le code sans aucun endroit pour le consulter ou le modifier sans
  reconstruire l'exe : fuseau horaire et tolérance de rattrapage du scheduler, niveau/rotation
  des logs, fréquences de rafraîchissement de l'UI (Dashboard, Pipelines, log en direct, traçage
  lumineux), plus un nouveau plafond d'exécutions simultanées (stocké et modifiable, pas encore
  appliqué — premier acte d'un futur chantier sur le suivi des ressources). Recherche + catégories
  à gauche, détail à droite, façon VSCode. La description de chaque champ précise s'il prend
  effet immédiatement ou seulement au prochain redémarrage.
- Les champs du digest de notification (résumé périodique par email) sont repris dans la
  catégorie "Notifications" de ce nouvel écran — le bouton 🔔 du Dashboard y amène directement.
  `NotificationSettingsDialog`, devenu redondant, est retiré.

## [0.26.1] - 2026-08-15

### Corrigé
- Étape Script Python : le dialogue de configuration (le plus long des dialogues d'étape) pouvait
  dépasser la hauteur disponible sur certains écrans, coupant les derniers champs sans zone de
  défilement — corrigé, boutons Annuler/Valider restant fixes en pied de fenêtre.

## [0.26.0] - 2026-08-15

### Ajouté
- Le dialogue d'exécution ("Exécuter maintenant") peut désormais être fermé à tout moment
  pendant l'exécution : "Fermer" laisse le pipeline continuer en arrière-plan (visible via le
  badge "RUNNING"), un nouveau bouton "Arrêter" demande l'interruption coopérative sans avoir à
  fermer puis relancer.
- Pipelines : nouvelle action "Interrompre l'exécution en cours" dans le menu "…" de chaque
  ligne, visible uniquement pendant qu'un run est effectivement en cours — accessible même après
  avoir fermé le dialogue de suivi (qui ne bloque plus la fermeture, voir ci-dessus).

### Corrigé
- Fermer le dialogue d'exécution pendant qu'un pipeline tournait provoquait un plantage de
  l'application dès la fin du run ("QThread: Destroyed while thread is still running") — le
  thread d'exécution n'était référencé que par un attribut Python du dialogue, insuffisant à lui
  seul pour le protéger du ramasse-miettes une fois qu'aucune variable ne référençait plus le
  dialogue fermé. Corrigé par une référence forte explicite, maintenue tant que le run continue.
- Pipelines : laisser le menu "…" d'une ligne ouvert pendant qu'un rafraîchissement automatique
  survenait (toutes les 30s) plantait l'application — reconstruit toute la colonne Actions (donc
  chaque menu) à chaque appel, y compris un menu actuellement affiché. Le rafraîchissement est
  désormais reporté tant qu'un menu contextuel est ouvert.

## [0.25.0] - 2026-08-15

### Ajouté
- Personnalité structurelle, vague 4 (suite des vagues 1-3, derniers éléments du backlog) :
  - Historique : calendrier de fréquence par pipeline (façon graphe de contributions, ~90
    derniers jours) — repérer un motif ("ce pipeline échoue tous les lundis") d'un coup d'œil.
    Survoler une case affiche le détail de ce jour précis ; cliquer une case avec au moins une
    exécution ouvre la liste des runs de ce jour (double-clic sur une ligne pour le log complet).
  - Éditeur graphique : traçage lumineux — le nœud de l'étape en cours d'une exécution réelle
    (et son arête entrante) se surlignent en direct, interrogé en continu tant que le dialogue
    est ouvert. Nouvelle colonne `current_step_key` (migration idempotente) pour identifier
    précisément l'étape, en plus du libellé humain déjà existant.

### Corrigé
- Un pipeline enregistré avec une fréquence Quotidien ou Cron ne s'exécutait jamais à l'heure
  prévue : l'enregistrement persistait bien la planification en base, mais ne prévenait jamais
  APScheduler du changement — le job n'était (re)créé qu'au prochain redémarrage de l'app ou à un
  aller-retour actif/inactif. Corrigé à la racine (planification immédiate à l'enregistrement,
  et aux deux autres points de création d'un pipeline en dehors de cette boîte de dialogue :
  raccourci "Nouveau (graphique)" et import).
- Pipelines : la colonne "Planification" affichait toujours l'heure quotidienne (ex: "CUSTOM
  06:00"), même pour une fréquence Personnalisée (Cron) où cette valeur n'est jamais utilisée —
  affiche désormais la véritable expression cron dans ce cas.
- Historique : la colonne "Statut" de la fenêtre de détail d'un jour du calendrier de fréquence
  se faisait compresser par Qt en dessous de sa largeur réelle (badge tronqué en plein mot) —
  même correctif de largeur fixe déjà appliqué ailleurs dans cette vue.

## [0.24.0] - 2026-08-16

### Ajouté
- **Vue globale des pipelines** (`ui/dialogs/pipeline_topology_dialog.py`) : nouvelle fenêtre
  dédiée montrant tous les pipelines en nœuds reliés par leurs chaînes de déclenchement, dans le
  même langage visuel que l'aperçu du Dashboard, mais sans plafond — zoom à la molette, recherche
  par nom, filtre par statut (En cours/Succès/Échec/Inactifs), clic sur un nœud pour ouvrir son
  détail. Ouverte via un nouveau lien "Voir tous les pipelines (N) →" sur le Dashboard, qui
  n'apparaît que lorsque l'aperçu (désormais plafonné à 6 chaînes racines pour rester lisible)
  laisse des pipelines de côté.

### Corrigé
- La disposition en nœuds de la Vue globale ne repassait jamais à la ligne (largeur de calcul
  fixée en dur bien au-delà de la fenêtre réelle) — tout s'étalait sur une seule rangée toujours
  plus large, fastidieuse à parcourir avec beaucoup de pipelines. Utilise désormais la largeur
  réelle de la fenêtre, et se réajuste au redimensionnement/plein écran.
- Échec de la duplication de pipeline dans l'exécutable gelé (« No module named
  'numpy._core._exceptions' ») — `numpy`/`pandas` (dépendance de `pandas`, utilisé pour
  l'export CSV) n'étaient déclarés qu'en `hiddenimports` simple, insuffisant pour leurs
  extensions C ; même traitement `collect_all()` que `oracledb` désormais appliqué aux deux.
  Préexistant, sans lien avec ce chantier — juste repéré en le testant.

## [0.23.0] - 2026-08-16

### Ajouté
- Personnalité structurelle, vague 3 (suite des vagues 1/2) :
  - Pipelines : vignette de flux (points colorés, un par étape) devant le résumé texte de chaque
    ligne, pour reconnaître un pipeline d'un coup d'œil.
  - Dashboard : la section "Activité (30 derniers jours)" (graphique en barres) est remplacée par
    "Vue d'ensemble des pipelines" — un aperçu des pipelines en nœuds reliés par leurs chaînes de
    déclenchement, colorés par leur dernier statut. Le graphique en barres reste utilisé tel quel
    dans la vue détail d'un pipeline.
  - Dashboard : le tableau "Dernières exécutions" passe d'un flux chronologique plat à une ligne
    par pipeline, avec une bande de pastilles montrant les dernières exécutions plutôt qu'un seul
    badge de statut.

### Corrigé
- Pipelines : le résumé d'étapes trop long se coupait en plein mot sans indication visuelle —
  troncature avec "…", texte complet toujours disponible en infobulle.
- Dashboard : les nœuds de la mini-topologie n'avaient pas de conteneur visuellement délimité,
  le point de statut n'était pas aligné avec le nom du pipeline, et un pipeline inactif n'avait
  qu'une bordure grise pleine (pas assez distincte d'un statut "en échec" au premier regard) —
  conteneur dédié, point en ligne avec le nom, bordure interrompue pour un pipeline inactif.

## [0.22.0] - 2026-08-15

### Ajouté
- Personnalité structurelle, vague 2 (suite de la vague 1) :
  - Dashboard : bloc santé asymétrique (anneau segmenté succès/échec + 4 cartes secondaires
    compactes — Succès, Échecs, Pipelines actifs, Durée moy.) remplace la grille de 3 cartes
    identiques. L'anneau ne compte que les pipelines actifs ayant déjà un dernier statut connu ;
    les pipelines jamais exécutés sont recensés à part dans la légende plutôt que d'être invisibles.
  - Séparateurs de section du Dashboard reprenant le motif "flux" (3 points reliés, rendu SVG)
    au lieu d'une ligne plate.
  - Connexions : icône de prise ajoutée à côté du badge d'état existant (OK/Échec/Jamais testé,
    inchangé) sur les 6 tableaux de profils.
  - Requêtes SQL : les mots-clés SQL (SELECT, FROM, WHERE…) sont désormais colorés dans
    l'infobulle d'aperçu de la requête.

### Corrigé
- Dashboard : le contenu (rail + bloc santé plus haut que ce qu'il remplace) pouvait dépasser la
  hauteur de la fenêtre sans zone de défilement, provoquant un chevauchement visuel — la vue
  défile désormais correctement.
- Connexions : la colonne "État" (badge OK/Échec/Jamais testé) et la nouvelle colonne "prise"
  pouvaient se faire compresser par Qt en dessous de leur besoin réel une fois le tableau plus
  chargé, rognant silencieusement le texte du badge — largeurs fixes désormais garanties.

## [0.21.0] - 2026-08-15

### Ajouté
- Personnalité structurelle, vague 1 (suite du chantier identité — la palette seule ne suffisait
  pas, la structure restait celle d'un dashboard générique) :
  - Chaque type d'étape a désormais sa propre icône (extraction, FTP, Spark SQL, script Python…),
    visible dans le sélecteur de type, l'éditeur linéaire et l'éditeur graphique — plus seulement
    une couleur.
  - Dashboard : rail « Prochaines & en cours » en tête de page (remplace la carte isolée
    « Prochaine exéc. ») — le pipeline en cours d'exécution y pulse, les prochains passages
    planifiés y sont listés.
  - Éditeur graphique : les arêtes portent désormais une flèche indiquant le sens du flux.
  - Badge « RUNNING » animé (légère pulsation) sur les 3 écrans qui l'affichent (Dashboard,
    Pipelines, Historique), via une fabrique commune.
  - Pipelines : un pipeline déclenché après un autre (chaînage) apparaît désormais indenté sous
    son parent plutôt que noyé alphabétiquement dans la liste.
  - Connexions : un profil non retesté depuis plus de 30 jours s'estompe légèrement dans le
    tableau, pour repérer d'un regard ce qui mérite d'être revérifié.

### Corrigé
- Les ~12 derniers endroits qui codaient encore `"Consolas"` en dur (éditeur de requête SQL,
  journal d'exécution, indices de tokens/cron, éditeurs de scripts Python/Spark/Sqoop) utilisent
  désormais `FONT_MONO`/`FONT_MONO_STACK` — scope explicitement laissé de côté lors de la phase 1
  de l'identité visuelle (v0.19.0), complété ici : JetBrains Mono s'applique maintenant partout
  dans l'application, sans exception.

## [0.20.0] - 2026-08-14

### Ajouté
- Identité visuelle, phase 2 : logo « flux de pipelines » (3 nœuds reliés) et les 6 icônes de la
  barre de navigation redessinés en traits personnalisés (`ui/icons.py`, tracés SVG embarqués,
  rendus via `QSvgRenderer` — remplacent les icônes Font Awesome utilisées jusqu'ici pour ces 7
  éléments ; le reste de l'application continue d'utiliser Font Awesome, inchangé). Cartes
  statistiques du Dashboard dotées d'un liseré de couleur (bleu-signal/vert/rouge/orange selon la
  carte). Petit indice contextuel (« N exécution(s) sur la période ») ajouté à côté du titre de la
  section Activité.

### Modifié
- Espacement du bloc logo de la barre de navigation aligné sur la maquette (18px au lieu de 16px).

### Corrigé
- Le logo utilisait un chemin de rendu différent des icônes de navigation (extraction manuelle
  `.pixmap()` depuis un pixmap source surdimensionné, plutôt que le pipeline normal
  `setIcon()`/`setIconSize()`), causant un espacement visuellement incorrect entre l'icône et le
  texte « DataScheduler ». Corrigé en rendant le logo directement à sa taille cible.

## [0.19.0] - 2026-08-14

### Modifié
- Identité visuelle : intégration de la maquette validée avec l'utilisateur (chantier design,
  2026-08). Polices IBM Plex Sans (interface) / JetBrains Mono (données tabulaires, logs)
  embarquées (`ui/fonts.py`, même convention que l'icône de `ui/branding.py` — pas de résolution
  de chemin dans l'exe gelé), avec repli silencieux vers Segoe UI/Consolas en cas d'échec
  d'enregistrement. Palette corrigée pour un vrai noir chaud (les fonds/textes étaient des gris
  neutres malgré le commentaire d'origine). Nouveau second accent « signal » (bleu-cyan sourd)
  qui reprend le statut « en cours » (badge RUNNING) — l'orange de la charte Orange SA ne porte
  plus que la marque et l'action primaire. Le bouton « Tout exécuter » du Dashboard passe en
  style secondaire (contour), son poids visuel correspondant désormais au niveau de risque réel
  de l'action.

### Corrigé
- Tableaux (`QTableWidget`) : suppression du rectangle de focus par défaut visible sur la cellule
  courante (ex : nom de pipeline dans « Dernières exécutions » du Dashboard) — relevé lors de
  l'audit de design, sans lien avec l'édition (déjà désactivée sur ces tableaux).

## [0.18.0] - 2026-08-13

### Ajouté
- Éditeur graphique : nouveau bouton « Planification & déclenchement… » qui ouvre directement
  l'éditeur classique du même pipeline pour son nom, sa planification et son déclenchement
  conditionnel — ces réglages restent gérés uniquement par l'éditeur classique (séparation des
  responsabilités inchangée), mais l'aller-retour "fermer, retrouver la ligne dans la liste,
  cliquer Modifier" n'est plus nécessaire.

## [0.17.0] - 2026-08-13

### Ajouté
- **Déclenchement conditionnel entre pipelines** : un pipeline peut désormais se lancer
  automatiquement à la fin d'un autre pipeline, selon une condition (Succès / Échec / Toujours),
  configurable dans une nouvelle section de l'éditeur de pipeline (« ④ Déclenchement
  conditionnel »). S'ajoute à la planification cron existante sans jamais la remplacer — un
  pipeline peut avoir les deux à la fois. L'infobulle de la colonne planification et le détail
  d'un pipeline indiquent la configuration active ; la suppression d'un pipeline avertit si
  d'autres en dépendent. Cette configuration reste volontairement locale à l'installation, elle
  n'est jamais incluse dans l'export/import d'un pipeline.

## [0.16.1] - 2026-08-12

### Corrigé
- Écran de revue de l'import de pipeline : les profils SSH, Kerberos et Élévation (ajoutés
  après cet écran) n'étaient pas reconnus — catégorie affichée en clé brute au lieu d'un libellé
  lisible, nom d'un profil réutilisé affiché "?", et surtout le menu « Remapper vers un profil
  existant » restait vide pour ces 3 catégories (impossible de réutiliser un profil déjà présent
  en local, un nouveau profil était systématiquement recréé à chaque import). Le texte d'aide du
  dialogue d'export, qui ne mentionnait pas ces 3 types de profil parmi les identifiants
  chiffrés, est aussi mis à jour.

## [0.16.0] - 2026-08-12

### Ajouté
- Étapes `SPARK_SQL`/`SQOOP_EXPORT` : l'étape courante affichée pendant l'exécution (infobulle,
  dialogue de log) distingue désormais précisément la connexion, l'authentification Kerberos,
  l'élévation (`sudo su`, si configurée) et **l'exécution de la requête/commande elle-même** —
  auparavant un seul libellé ("Authentification Kerberos…") restait affiché sans changer pendant
  toute la durée de l'appel, y compris quand la vraie requête tournait déjà depuis longtemps sur
  le cluster, rendant impossible de distinguer une authentification bloquée d'un traitement long
  mais normal.

## [0.15.0] - 2026-08-11

### Ajouté
- Visibilité d'un pipeline **pendant** son exécution, plus seulement une fois terminée :
  l'étape en cours et le log s'écrivent désormais en continu dans l'historique, pas en un seul
  bloc à la toute fin. Concrètement : l'étape courante apparaît en infobulle sur le badge
  « RUNNING » de la liste des pipelines, et le dialogue « Voir le log complet » se rafraîchit
  automatiquement (log + étape) tant que le run qu'il affiche est toujours en cours.
- Nettoyage automatique, au démarrage de l'application, de tout run resté affiché « en cours »
  suite à un arrêt brutal de la session précédente (crash, fermeture forcée) — marqué en échec
  avec un message explicite plutôt que de rester indéfiniment bloqué sur « RUNNING ».

## [0.14.0] - 2026-08-10

### Ajouté
- Profil SSH (nœud edge/master) : chaînage **bastion / jump host**. Un profil peut désormais
  déclarer qu'il n'est joignable qu'en passant d'abord par un autre profil SSH (« Via bastion »
  dans le dialogue de profil et l'onglet **Connexions** → « Big Data / Spark SQL »), pour les
  clusters où un nœud (ex : `edge03`) n'est accessible qu'en rebondissant depuis un autre
  (`edge01`) — cas réel remonté par une équipe utilisant Sqoop derrière un bastion. Chaîne de
  longueur arbitraire (récursif), pas seulement 2 sauts. Comme ce chaînage est résolu au point de
  connexion SSH unique de l'application (`core/hadoop_edge.py::_connect`), toutes les étapes
  concernées (`SPARK_SQL`, `SQOOP_EXPORT`), le tableau de bord de santé des connexions, le mode
  simulation (dry-run) et les boutons de test des profils Kerberos/Élévation en bénéficient
  automatiquement, sans aucune reconfiguration de pipeline existant.
- Export/import de pipeline : un profil SSH utilisé uniquement comme bastion (jamais référencé
  directement par une étape) est désormais inclus dans le bundle et recréé/câblé correctement à
  l'import, quel que soit l'ordre d'apparition des profils dans le fichier.

## [0.13.0] - 2026-08-10

### Ajouté
- Étape `SQOOP_EXPORT` : nouveau profil d'**élévation de privilèges** (`sudo su`), pour les
  équipes qui basculent vers un compte technique partagé (ex : « nifi ») après connexion SSH,
  plutôt que d'utiliser Kerberos. Le mot de passe partagé est chiffré au repos comme tout autre
  profil, jamais en clair dans la configuration de l'étape ni dans les journaux d'exécution.
  Élévation et Kerberos sont désormais tous deux **facultatifs** sur cette étape (l'un, l'autre,
  les deux, ou aucun), configurables dans **Connexions** → onglet « Big Data / Spark SQL ».
- `core/hadoop_edge.py` : nouveau moteur d'exécution à canal shell interactif persistant
  (`run_command_with_elevation`), nécessaire pour enchaîner élévation + kinit optionnel + la
  commande réelle dans une même identité — un `sudo su` réussi ne survit jamais à un
  `exec_command()` séparé, contrairement à ce que le modèle d'exécution précédent permettait.
  Utilisé uniquement quand un profil d'élévation est configuré ; le chemin existant (sans
  élévation) reste strictement inchangé.

### Corrigé
- Étape `SQOOP_EXPORT` : le profil Kerberos, rendu obligatoire par erreur dès la conception
  initiale, est maintenant facultatif — certaines équipes n'en ont jamais eu besoin pour Sqoop.

## [0.12.0] - 2026-08-10

### Ajouté
- Nouveau type d'étape `SQOOP_EXPORT` : exporte une table Hive/HCatalog vers Oracle via `sqoop
  export`, sur un nœud edge (même mécanique de connexion que Spark SQL : SSH + authentification
  Kerberos). Les identifiants Oracle cible viennent d'un profil existant (jamais de champ texte
  libre en clair dans la configuration de l'étape) ; le mot de passe n'apparaît jamais dans les
  journaux d'exécution (commande masquée avant toute journalisation). Base HCatalog, table
  HCatalog source et table Oracle cible acceptent les jetons (`{yyyy}`, `{MM}`...).
- `core/hadoop_edge.py` (nouveau) : mécanique SSH/Kerberos extraite de `core/spark.py` pour être
  partagée avec `SQOOP_EXPORT` — refactor sans changement de comportement, `core/spark.py`
  ré-exporte les noms historiquement importés depuis là.

## [0.11.0] - 2026-08-07

### Ajouté
- Reprise depuis l'échec : quand un pipeline échoue ou est interrompu après qu'au moins une
  étape a réussi, une action « Reprendre depuis l'échec » (menu « ⋯ » de Pipelines, bouton
  proposé après un échec dans la fenêtre d'exécution, ou depuis le log d'un run) relance le
  pipeline en sautant les étapes déjà réussies plutôt que de tout rejouer depuis le début. Les
  artefacts produits par ces étapes sont préservés (non nettoyés) tant qu'ils n'ont pas été
  consommés par une reprise ou remplacés par un nouveau run. La reprise est refusée proprement
  (message clair, pas de crash) si le pipeline a été modifié depuis l'échec ou si un fichier
  temporaire a expiré entre-temps. Fonctionne aussi bien en mode linéaire qu'en mode graphe, y
  compris pour restaurer la bonne branche active d'un routeur `CONDITION` déjà résolu.

## [0.10.0] - 2026-08-07

### Ajouté
- Délai maximal configurable par étape (« Délai maximal », 0 = aucune limite, dans la politique
  d'exécution commune à tous les types d'étape). Une étape qui dépasse ce délai (ex : connexion
  SSH/Spark, FTP ou appel HTTP resté bloqué) est marquée en échec proprement au lieu de geler le
  pipeline indéfiniment ; le pipeline continue normalement ensuite (relance, `run_always`,
  reste des étapes). Limite assumée : CPython ne peut pas interrompre un appel bloquant de
  force — le pipeline avance, mais l'appel sous-jacent peut se terminer en arrière-plan plus
  tard sans effet sur l'exécution déjà passée à la suite (voir le commentaire de
  `_run_step_with_policy` dans `core/pipeline.py`).

## [0.9.0] - 2026-08-07

### Ajouté
- Étape `EMAIL_NOTIFY` : garde-fou de taille sur la pièce jointe (« Taille max. pièce jointe »,
  0/vide = aucune limite). Au-delà, deux comportements configurables (« Si dépassement ») :
  échouer le pipeline (par défaut) ou ignorer la pièce jointe et envoyer l'email quand même.
  Évite qu'une limite de taille imposée par un serveur mail d'entreprise ne surgisse en aval
  sous la forme d'une exception SMTP brute. Se combine avec la nouvelle étape `COMPRESS` pour
  réduire la taille du fichier en amont.

## [0.8.0] - 2026-08-07

### Ajouté
- Nouveau type d'étape `COMPRESS` : compresse le fichier de contexte (ou une source explicite/
  ciblée) en archive ZIP — utile pour réduire la taille d'un fichier avant diffusion (email, FTP),
  notamment quand un serveur mail d'entreprise limite la taille des pièces jointes. Conçue dès le
  départ avec les 3 modes de source (étape précédente par défaut, Source ciblée explicitement,
  chemin explicite manuel) plutôt qu'en retrofit ultérieur.

## [0.7.0] - 2026-08-06

### Ajouté
- Bouton "Télécharger un modèle de script" sur l'étape `PYTHON_SCRIPT` — enregistre un fichier
  `.py` commenté et fonctionnel, couvrant les 3 cas d'usage (script autonome, lecture de
  `{ds_context_in}`, publication via `{ds_context_out}`) pour quelqu'un qui découvre l'application
  et doit y brancher son propre script sans lire le code source de DataScheduler.

## [0.6.6] - 2026-08-06

### Corrigé
- Étape `PYTHON_SCRIPT` : un script en échec ne remontait que "Script terminé avec le code N" —
  la vraie raison (dernière ligne de stderr, en général le message d'exception d'un traceback)
  était loggée ligne par ligne mais absente du message d'erreur principal. Ajoutée comme
  premier indice, sans remplacer le log complet déjà disponible.

## [0.6.5] - 2026-08-06

### Corrigé
- Étape `PYTHON_SCRIPT` : le champ "Exécutable Python" était pré-rempli avec `sys.executable`
  (trompeur — voir 0.6.4) et jamais validé. Devenu un champ obligatoire (comme le chemin du
  script), plus jamais pré-rempli automatiquement ; tooltip corrigé.

## [0.6.4] - 2026-08-06

### Corrigé
- Étape `PYTHON_SCRIPT` : dans l'`.exe` packagé, `sys.executable` (valeur par défaut du champ
  "Exécutable Python", présentée comme sûre par le tooltip) est le chemin de DataScheduler.exe
  lui-même, pas un interpréteur Python (piège déjà documenté dans `docs/COOKBOOK.md`, jamais
  protégé jusqu'ici). Une étape gardant ce défaut ne lançait pas le script : elle relançait une
  deuxième instance complète de l'application et restait bloquée jusqu'au timeout. Détecté et
  refusé proprement au démarrage de l'étape, avec un message explicite.

## [0.6.3] - 2026-08-06

### Corrigé
- L'icône de l'exe (`DataScheduler.spec`) ne suffisait pas : Qt ne la reprend pas
  automatiquement pour la fenêtre une fois affichée — la barre de titre, le bouton de la barre
  des tâches pendant l'exécution et Alt-Tab montraient toujours l'icône générique Qt par
  défaut. `QApplication.setWindowIcon()` ajouté (`ui/branding.py`, icône encodée en base64 pour
  éviter toute résolution de chemin `sys._MEIPASS` dans l'exe gelé). Vérifié en extrayant
  l'icône réelle de la fenêtre en cours d'exécution (`WM_GETICON`), pas seulement celle de
  l'exe.

## [0.6.2] - 2026-08-06

### Corrigé
- Aucune icône d'application (`icon=None` dans `DataScheduler.spec`) — l'exe tournait avec
  l'icône générique par défaut dans la barre des tâches, l'Explorateur et le sélecteur Alt-Tab
  (audit de design). Logo fourni par l'utilisateur, converti en `.ico` multi-résolution
  (16 à 256px) — `assets/icon.ico`, `assets/icon.png`.

## [0.6.1] - 2026-08-06

### Corrigé
- Couleur "warning" identique à l'accent de marque (#FF7900) — un avertissement était
  visuellement indissociable d'un bouton actif ou survolé. Remplacée par un ambre doré
  (#E8B339), distinct sans sortir de la même famille chaude (audit de design).

### Ajouté
- `FONT_SIZES` (`ui/styles.py`) — les 6 paliers typographiques déjà utilisés de fait dans
  l'application, déclarés comme référence pour toute nouvelle vue (usages existants non migrés
  pour l'instant, zéro risque de régression).

## [0.6.0] - 2026-08-06

### Ajouté
- SPARK_SQL : configuration du fichier récupéré (séparateur, encodage, guillemets), mêmes
  options que l'étape Extraction base de données — auparavant impossible à régler. La sortie
  brute de spark-sql (tabulée, sans guillemets) est reformatée en CSV véritable par le step ;
  l'en-tête de colonnes est désormais toujours inclus (injection automatique de
  `--conf spark.sql.cli.print.header=true`, sauf si l'étape en fournit déjà un explicitement).

## [0.5.0] - 2026-08-06

### Ajouté
- Bouton "Nouveau (graphique)" sur Pipelines — crée un pipeline directement dans l'éditeur
  graphique (juste un nom), sans passer par l'éditeur classique qui imposait au moins une étape
  avant d'enregistrer.

## [0.4.0] - 2026-08-06

### Ajouté
- Vérification de compatibilité des types au moment de l'import d'un pipeline — bloque
  proprement un bundle référençant un type d'étape ou de profil inconnu de cette version de
  l'application, au lieu d'échouer confusément plus tard (à l'édition ou à l'exécution).

## [0.3.0] - 2026-08-06

### Ajouté
- Étape `SPARK_SQL` : requêtes Spark SQL sur un cluster Hadoop via un nœud edge (SSH +
  authentification Kerberos automatisée), avec 2 nouveaux types de profil (SSH, Kerberos).
- Section Aide intégrée (8 rubriques) et graphique d'activité sur le Dashboard.
- Fiabilité opérationnelle : duplication de pipeline, validation à blanc, vue détaillée par
  pipeline, bilan de santé des connexions.
- Journal des modifications (audit trail) consultable depuis l'Historique.
- Ergonomie multi-pages : confirmation avant "Tout exécuter", filtre de statut sur
  l'Historique (cartes du Dashboard cliquables), consolidation des actions Pipelines,
  restructuration de Connexions en onglets avec statut de santé inline, colonne "Utilisée par"
  sur Requêtes SQL, recherche étendue au contenu sur l'Aide, messages d'état vide pédagogiques.
- Ce fichier et la politique de version qui l'accompagne.

### Corrigé
- Chaînage d'un producteur de fichier "dynamique" (ex : `SPARK_SQL` avec résultat récupéré)
  vers une étape en aval, en éditeur graphique comme linéaire — la publication de l'artefact
  se fiait à une déclaration statique qui ne peut pas exprimer une production conditionnelle à
  la configuration.
- Sélecteur "Source" de l'éditeur d'étape : un producteur dynamique n'y apparaissait jamais,
  quelle que soit sa configuration.
- Boutons d'actions se chevauchant visuellement (Pipelines, Requêtes SQL) — largeur de colonne
  fixée par code mais mode de redimensionnement resté automatique.
- Libellé trompeur "CSV-like" sur le résultat Spark SQL récupéré (format réel : tabulé, sans
  séparateur virgule).
- 5 incohérences trouvées en relisant les 10 implémentations de step (résolution de jetons
  manquante sur DB_EXTRACT, faux positif de validation, fuite de connexion et de fichier
  temporaire, fréquence de digest de notifications figée en dur).
- Notification manquante sur l'échec d'un pipeline *planifié* (`run_pipeline()` ne lève jamais
  d'exception ; seul le déclenchement manuel vérifiait le résultat).
- Export/import d'un pipeline en graphe perdant silencieusement ses arêtes au réimport.

### Sécurité
- Mots de passe de profils chiffrés au repos (Fernet, clé maître dérivée via DPAPI Windows).
- Identité stable (UUID) sur les entités réutilisables — prérequis à l'export/import portable.

## [0.2.0]

Version de référence au démarrage de ce fichier — voir l'historique Git de
`feature/hardening-foundations` pour le détail antérieur : fondations de sécurité et d'identité,
refonte du modèle d'exécution (artefacts nommés, contrat JSON pour les scripts Python,
export/import versionné et chiffré, moteur d'exécution en graphe/DAG), assainissement de
l'architecture UI.
