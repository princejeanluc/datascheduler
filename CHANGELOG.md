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
