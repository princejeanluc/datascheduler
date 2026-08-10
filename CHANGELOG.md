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
