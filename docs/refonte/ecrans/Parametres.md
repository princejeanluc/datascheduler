# Paramètres

Vue : `ui/main_window/settings_view.py`. Maquettes : `maquettes/png/Parametres*.png`.

## Intention
L'écran règle le comportement de Kulu sur ce poste. La disposition (recherche et catégories à gauche, réglages à droite) a été validée et ne change pas. La refonte ajoute deux choses : dire pour chaque réglage quand il prend effet, et rendre visibles les modifications non enregistrées et les erreurs.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Parametres | Catégorie Ordonnanceur, rien de modifié | ouverture de l'écran |
| Parametres-recherche | Résultats « rafraîch » dans toutes les catégories | saisie dans « Rechercher un paramètre… » |
| Parametres-arriere-plan | Mode d'exécution passé à « Avec exécution en arrière-plan », pas encore enregistré | choix dans la liste Mode d'exécution |
| Parametres-refus | Windows refuse la tâche d'arrière-plan | Enregistrer quand `register_logon_task()` échoue |
| Parametres-notifications | Résumé hebdomadaire, champ Jour affiché | Fréquence = Hebdomadaire |
| Parametres-validation | Trois champs invalides | Enregistrer avec profil SMTP vide, destinataires vides, heure « 8h00 » |
| Parametres-enregistre | Enregistrement réussi, un réglage en attente de redémarrage | Enregistrer réussi |

## À garder tel quel
- Les 5 catégories et leur ordre (`_CATEGORIES`) : Ordonnanceur, Journalisation, Interface, Notifications, Ressources.
- Toutes les lignes créées dans `_build_rows`, avec leurs bornes et suffixes (`setRange`, `setSuffix`, `setSpecialValueText("Aucune")` pour la marge Kerberos).
- Le fuseau horaire : liste IANA complète (`_TIMEZONES`, UTC en tête) avec complétion.
- La recherche porte sur le libellé et la description (`_on_search_changed`), et affiche la catégorie de chaque résultat.
- Le champ « Jour » n'apparaît qu'en hebdomadaire et hors recherche (`_on_frequency_changed`).
- `select_category(key)` est public : le raccourci 🔔 du Dashboard l'appelle pour ouvrir Notifications. Garde son nom et son comportement.
- L'enregistrement unique et explicite (`_on_save`), et tout son déroulé : écriture des réglages, `request_reload()` ou `apply_settings()` puis `refresh_digest_job()`, changement de niveau de log immédiat.
- La bascule de mode : `register_logon_task()` en passant en arrière-plan, avec retour automatique à « Dans l'application seulement » en cas d'échec ; `unregister_logon_task()` et `enqueue_worker_command("SHUTDOWN")` au retour. Ce filet évite un état où plus aucun pipeline planifié ne tourne : il ne doit pas disparaître.
- L'état du worker déduit du dernier échantillon (`_refresh_worker_status`), périmé au-delà de deux fois l'intervalle.
- La confirmation non bloquante après enregistrement (choix volontaire, voir le commentaire dans `_on_save`).

## Lot A : alignement visuel, sans changer la base
| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | Rail de gauche : icône, nom et sous-titre par catégorie ; catégorie active sur `bg_active` avec liseré `accent` | Parametres | `_CATEGORIES` |
| A2 | En-tête de page : surtitre « CE POSTE · KULU <version> », titre « Paramètres » | Parametres | `version.__version__` |
| A3 | Lignes : libellé 14 px, description 12,5 px `text_dim`, contrôle à droite, séparateur `bg_hover` | Parametres | `_add_row` |
| A4 | Pastille de prise d'effet sur chaque ligne : « immédiat », « à la prochaine ouverture » ou « au redémarrage ». Utilise le paramètre `badge` de `_add_row`, aujourd'hui jamais renseigné. Retire « Redémarrage requis » des descriptions, puisque la pastille le dit | Parametres, -recherche | descriptions actuelles de `_build_rows` (voir tableau plus bas) |
| A5 | Recherche : nombre de résultats par catégorie dans le rail, catégories sans résultat estompées, mot cherché surligné, ligne d'aide « N réglages dans M catégories » | Parametres-recherche | `_on_search_changed` |
| A6 | État du worker : point vert « Actif · signal il y a N s », rouge « Arrêté », ou texte discret « Sans objet » en mode application | Parametres | `_refresh_worker_status` |
| A7 | Échec « accès refusé » en bandeau d'échec en haut du panneau, au lieu du texte rouge du pied qui disparaît après 10 s. Le bandeau reste jusqu'à fermeture ou nouvel enregistrement | Parametres-refus | `_on_save`, `background_activation_failed` |
| A8 | Pied du panneau : état à gauche, raccourci « Ctrl S » et bouton Enregistrer à droite | toutes | `_save_status_lbl` |

Prise d'effet à afficher, d'après les descriptions actuelles du code :

| Réglage | Pastille |
|---|---|
| Fuseau horaire, Mode d'exécution, Taille max par fichier, Fichiers conservés, Rafraîchissement Dashboard, Rafraîchissement Pipelines | au redémarrage |
| Log d'exécution en direct, Traçage lumineux | à la prochaine ouverture |
| Intervalle d'échantillonnage, Tolérance de rattrapage, Regrouper les rattrapages (réappliqués par `apply_settings()`) | immédiat |
| Plafond d'exécutions simultanées (relu à chaque lancement, `core/pipeline.py`), Kerberos (relus à chaque étape Sqoop ou Spark), Niveau de journalisation (`setLevel` dans `_on_save`) | immédiat |
| Résumé par email (tous ses champs, `refresh_digest_job()`) | immédiat |
| Rétention des échantillons | immédiat (appliquée à la prochaine mesure) |

## Lot B : changements de données
Aucun changement de schéma. Toutes les valeurs existent déjà dans `AppSettings` et `NotificationSettings`.

## Lot C : fonctions nouvelles (« proposé »)
| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Modifications non enregistrées : liseré `accent` et point sur chaque ligne modifiée, compteur par catégorie dans le rail, « N réglages modifiés · non enregistrés » et « Annuler les modifications » dans le pied. Enregistrer est grisé sans modification | -arriere-plan, -notifications | valeurs chargées par `_prefill`, à mémoriser pour comparer |
| C2 | Encart « Ce qui se passe à l'enregistrement » sous Mode d'exécution quand on choisit l'arrière-plan : tâche Windows, refus possible, redémarrage | -arriere-plan | `core/task_scheduler.py` |
| C3 | Validation en ligne : message sous chaque champ invalide, tous à la fois, bandeau « N champs à corriger. Rien n'a été enregistré ». Remplace les `QMessageBox.warning` de `_on_save` sans changer les règles de validation | -validation | `_on_save`, `_is_valid_time` |
| C4 | Après enregistrement : bandeau qui nomme ce qui s'applique tout de suite et ce qui attend un redémarrage, boutons « Redémarrer Kulu » et « Plus tard » ; pastille « en attente de redémarrage » sur les lignes concernées | -enregistre | C1 (savoir ce qui a changé), A4 |
| C5 | Résumé par email : « Prochain envoi : <jour> à <heure> », contenu prévu (nombre de runs et d'échecs), « Envoyer un essai à moi », « Voir l'aperçu » | -notifications | `core/scheduler.py::refresh_digest_job`, `_run_digest`, `_build_digest_body` |
| C6 | Profil SMTP : date du dernier test du profil choisi | -notifications | `record_profile_test_result` |
| C7 | Ctrl F met le curseur dans la recherche, Échap la vide, Ctrl S enregistre | -recherche | nouveau |
| C8 | « Copier le détail » dans le bandeau de refus | -refus | nouveau |

## Hors périmètre
- Le thème clair.
- L'état du worker rafraîchi en continu (manquement noté, à traiter avec l'exécution à distance).
- Un réglage nouveau qui n'existe pas dans `AppSettings`.

## Critères d'acceptation
- [ ] Les 5 catégories et toutes les lignes actuelles sont présentes, dans le même ordre, avec les mêmes bornes.
- [ ] `select_category("notifications")` ouvre toujours Notifications depuis le Dashboard.
- [ ] Chaque ligne listée dans le tableau de prise d'effet porte la bonne pastille, et aucune description ne répète « Redémarrage requis ».
- [ ] Une recherche « rafraîch » montre les 4 réglages d'Interface, le compteur 4 sur Interface et les autres catégories estompées. Échap revient à la catégorie active.
- [ ] En hebdomadaire, Jour apparaît ; en quotidien, il disparaît ; pendant une recherche, il suit le résultat.
- [ ] Un test simule l'échec de `register_logon_task()` : le mode revient à « Dans l'application seulement » en base, et le bandeau d'échec s'affiche puis reste visible.
- [ ] Le retour au mode application envoie toujours `SHUTDOWN` au worker (test existant `tests/test_execution_mode.py` vert).
- [ ] Avec profil SMTP vide, destinataires vides et heure « 8h00 », les trois messages s'affichent ensemble et rien n'est écrit en base (C3).
- [ ] Modifier deux réglages affiche « 2 réglages modifiés » ; « Annuler les modifications » remet les valeurs chargées (C1).
- [ ] `tests/test_settings_view.py` et `tests/test_app_settings_scheduler_wiring.py` restent verts.
- [ ] Captures des 7 états jointes à la PR.

## Questions ouvertes
- En mode arrière-plan, `_on_save` appelle `request_reload()` au lieu de `apply_settings()` : vérifie que le worker réapplique bien les réglages « immédiat » à réception, sinon leur pastille doit dire « au prochain cycle du worker ».
- C4 « Redémarrer Kulu » : relancer l'exécutable proprement sous Windows (PyInstaller) doit être vérifié. Si c'est risqué, garde seulement le message et « Plus tard ».
