# Connexions

Vue : `ui/main_window/connections_view.py` (et dialogues liés : `ui/dialogs/oracle_dialog.py`, `database_profile_dialog.py`, `ftp_dialog.py`, `smtp_dialog.py`, `ssh_profile_dialog.py`, `kerberos_profile_dialog.py`, `elevation_profile_dialog.py`, `connection_health_dialog.py`). Maquettes : `maquettes/png/Connexions*.png`.

## Intention
Un profil data doit voir d'un coup d'œil quelles connexions sont cassées, lesquelles n'ont jamais été testées et quels pipelines en dépendent, puis réparer sans quitter l'écran. La refonte remplace six tableaux répartis dans trois onglets par une liste unique groupée par famille, avec la date du dernier test, l'usage par les pipelines et un test par ligne, et donne au bilan de santé et à la suppression les informations qui manquent pour décider.

## États (frames)
| Frame | Ce qu'elle montre | Déclencheur dans l'application |
|---|---|---|
| Connexions | Liste groupée (Bases de données, Fichiers et e-mail, Big Data), filtres à gauche, en-tête avec compteurs | Clic sur « Connexions » dans la navigation |
| Connexions-detail | Panneau latéral d'une connexion : bandeau d'état, paramètres, pipelines qui l'utilisent, historique des tests | Clic sur une ligne |
| Connexions-nouvelle | Modale « Vers quoi Kulu doit-il se connecter ? » avec 9 types en 3 familles | Bouton « + Nouvelle connexion » |
| Connexions-formulaire | Modale de modification (exemple SFTP) avec bandeau d'échec du test | « Modifier », puis « Tester la connexion » en échec |
| Connexions-sante | Modale « Bilan de santé » pendant le test (7/12, OK, échecs, en test, en attente) | Bouton « Bilan de santé » |
| Connexions-suppression | Modale de suppression d'une connexion utilisée par deux pipelines | « Supprimer » dans le panneau ou la ligne |

## À garder tel quel
- Les 7 types de profils et leurs tables : `OracleProfile`, `DatabaseProfile` (MySQL, PostgreSQL, SQL Server), `FtpProfile`, `SmtpProfile`, `SshProfile`, `KerberosProfile`, `ElevationProfile` (`database/models.py`), et les fonctions CRUD de `database/db_manager.py`.
- Le regroupement par usage en 3 groupes, dans cet ordre : Bases de données ; Fichiers et notifications (FTP puis SMTP) ; Big Data (SSH, Kerberos, Élévation). Aujourd'hui ce sont les 3 onglets de `ConnectionsView._build_ui`, vérifiés par `tests/test_connections_view_tabs_and_health.py` (voir Questions ouvertes, point 1).
- Tous les champs de chaque formulaire :
  - Oracle (`OracleDialog`) : nom, hôte, port (1521), mode Service Name ou SID et le champ correspondant, utilisateur, mot de passe, mode d'authentification (Standard, SYSDBA, SYSOPER) avec l'avertissement SYS, délai de test de 30 s (`_on_test_timeout`).
  - MySQL, PostgreSQL, SQL Server (`DatabaseProfileDialog`) : nom, hôte, port par défaut selon le moteur (`DEFAULT_PORTS`), utilisateur, mot de passe, base ou schéma ; pour SQL Server les cases « Chiffrer la connexion (Encrypt) » et « Faire confiance au certificat serveur » stockées dans `extra_json`.
  - FTP (`FtpDialog`) : nom, hôte, port, protocole FTP, FTPS ou SFTP, port qui passe à 22 ou 21 au changement de protocole (`_on_protocol_changed`), utilisateur, mot de passe, dossier distant (non enregistré, voir Lot B).
  - SMTP (`SmtpDialog`) : nom, hôte, port 587, case STARTTLS, utilisateur et mot de passe facultatifs, adresse expéditeur obligatoire.
  - SSH (`SshProfileDialog`) : nom, hôte, port 22, utilisateur, mot de passe, « Via bastion (optionnel) » qui exclut le profil lui-même ; refus des cycles (`_ssh_jump_chain_has_cycle`).
  - Kerberos (`KerberosProfileDialog`) : nom, principal, mot de passe, note sur le compte nominatif, test kinit qui exige de choisir un profil SSH.
  - Élévation (`ElevationProfileDialog`) : nom, utilisateur cible, mot de passe, note sur le compte partagé, test sudo su qui exige un profil SSH.
- Le choix du moteur avant la création d'un profil de base (`DbTypeChooserDialog`, `DB_TYPE_META`).
- Le test de connexion dans chaque formulaire : il utilise les valeurs saisies, réutilise le mot de passe enregistré si le champ est vide en modification, tourne dans un `QThread`, et enregistre le résultat par `record_profile_test_result` quand le profil existe déjà.
- Mot de passe obligatoire à la création, champ vide en modification = mot de passe conservé (`_validate`, `update_*_profile(password=None)`), indication « laisser vide pour conserver ».
- Validation des champs obligatoires avec bordure `danger` et texte d'aide dans le champ.
- L'état du dernier test : OK, Échec, Jamais testé, avec le mot et pas seulement la couleur (`_health_badge`), l'estompage au-delà de 30 jours (`_STALE_AFTER_DAYS`) et l'icône de prise (`_connection_indicator`).
- La recherche, qui filtre toutes les listes à la fois (`_on_search_changed`).
- Les états vides de chaque groupe (`_make_empty_label`, textes actuels).
- Le bilan de santé : test séquentiel dans un thread (`_HealthCheckThread`), enregistrement de chaque résultat, Kerberos signalé « non testable ici » sans être compté comme un échec (`_test_one` renvoie `None`), fermeture bloquée pendant le test (`closeEvent`).
- Avant suppression, l'avertissement qui nomme les pipelines concernés (`find_pipelines_using_profile`, `find_pipelines_using_db_profile`) et, pour un profil SSH, les profils qui l'utilisent comme bastion et repasseront en connexion directe (`find_ssh_profiles_using_as_bastion`).
- Sécurité : les mots de passe restent chiffrés au repos par `database/crypto.py` (clé Fernet dans le gestionnaire d'identification). Aucun écran, ancien ou nouveau, n'affiche un secret en clair : le panneau de détail écrit « enregistré, chiffré sur ce poste », les champs restent en `QLineEdit.Password`, et aucun message de test, journal ou historique ne contient un mot de passe déchiffré.

## Lot A : alignement visuel, sans changer la base
Lot A restyle l'existant et peut afficher une valeur déjà renvoyée par une fonction existante. Il ne crée ni comportement ni fonction de données.

| # | Changement | Frame | Source des données (code) |
|---|---|---|---|
| A1 | En-tête de page (FONDATIONS §3) : titre « Connexions », recherche « Nom, hôte, utilisateur… », bouton secondaire « Bilan de santé » | Connexions | `_build_ui`, `_on_search_changed`, `_on_health_check` |
| A2 | Surtitre « 12 CONNEXIONS · 1 EN ÉCHEC · 1 JAMAIS TESTÉE », compté sur les listes déjà chargées | Connexions | `list_all_db_profiles`, `get_*_profiles`, `last_test_success` |
| A3 | Lignes à deux niveaux : nom en 14 px et type en dessous ; cible en Mono (`hôte:port`) et utilisateur ou expéditeur en dessous ; « SMTP · STARTTLS » | Connexions | `_refresh_*` ; `p.use_tls`, `p.from_address`, `p.protocol` |
| A4 | Cible SSH « via Bastion DMZ » et « bastion de Edge Hadoop » | Connexions | `p.jump_via_id`, `find_ssh_profiles_using_as_bastion` |
| A5 | Colonne « Dernier test » : pastille de statut puis heure lisible (« 07:28 aujourd'hui », « il y a 41 jours · à retester ») au lieu de l'infobulle | Connexions | `last_test_success`, `last_tested_at` (sauf bases, voir B2), `fmt_relative` (FONDATIONS §4) |
| A6 | Colonne « Utilisée par » : « 1 pipeline », « 2 pipelines », « aucun pipeline » en `text_muted` | Connexions | `find_pipelines_using_profile`, `find_pipelines_using_db_profile` |
| A7 | Icône de famille dans une pastille de 28 px, couleur de famille (FONDATIONS §1) | Connexions | type du profil |
| A8 | Formulaires en fenêtre modale (FONDATIONS §3) : surtitre « MODIFIER · FICHIERS », icône et nom ; libellé « Nom de la connexion * » ; FTP en sélecteur segmenté FTP, FTPS, SFTP ; aide « 22 par défaut en SFTP » sous le port | Connexions-formulaire | `FtpDialog._build_ui`, `PROTOCOLS`, `_on_protocol_changed` |
| A9 | Résultat du test en bandeau (réussite ou échec, FONDATIONS §3) avec l'heure (« Le test a échoué à 15:42 ») et le message brut en Mono ; pied « Le test utilise les valeurs saisies, pas celles enregistrées. », « ⚡ Tester la connexion », « Annuler », « Enregistrer » | Connexions-formulaire | `_on_test_result` des 7 dialogues |
| A10 | Bilan de santé restylé : surtitre « BILAN DE SANTÉ », titre « Test de toutes les connexions », sous-titre, une ligne par profil avec icône, nom, statut, message en clair (aujourd'hui en infobulle), heure relative | Connexions-sante | `ConnectionHealthDialog`, `_render_row`, `_on_row_tested` |
| A11 | Modale de suppression : surtitre « SUPPRIMER » en `danger`, titre « Supprimer SFTP Partenaire ? », texte et liste des pipelines, « Annuler », « Supprimer quand même » | Connexions-suppression | `_confirm_delete` |
| A12 | Les heures passent par `ui/time_display.py` ; supprimer le `strftime` direct de `_render_row` | Connexions, Connexions-sante | FONDATIONS §4 |

## Lot B : changements de données

> Le schéma de référence est dans `../DONNEES.md`. Si un nom ou une colonne diffère ici, c'est `DONNEES.md` qui fait foi.

- **B1. Dossier distant FTP.** Le champ existe dans `FtpDialog` mais n'est ni enregistré ni relu : `FtpProfile` n'a pas de colonne, `_on_save` l'ignore. Proposition : `ALTER TABLE ftp_profiles ADD COLUMN remote_dir VARCHAR(500)` (nullable) dans `_migrate`, paramètre `remote_dir=None` sur `create_ftp_profile` et `update_ftp_profile`. Worker : l'ancien code ignore la colonne. Export : ajouter le champ à `_serialize_ftp_profile` change le format (version 4 et transcripteur) ; à décider (Questions, point 4).
- **B2. Date du dernier test des bases.** `list_all_db_profiles` ne renvoie pas `last_tested_at`, donc l'estompage à 30 jours ne marche pas pour les bases. Ajouter la clé au dict, et `service_name`, `sid`, `database_name` pour la cible « hôte:port / CRMP ». Aucune colonne.
- **B3. Historique des tests.** Seul le dernier résultat est gardé, sans message. Nouvelle table `profile_test_results` (`id`, `category`, `profile_id`, `tested_at` UTC, `success`, `message` TEXT, `duration_ms` NULL, `via_ssh_profile_id` NULL). `record_profile_test_result` reçoit `message=None, duration_ms=None, via_ssh_profile_id=None` en mots-clés et continue de remplir `last_tested_at` et `last_test_success`. Le message est enregistré après retrait de tout mot de passe déchiffré qu'il contiendrait. Garder au plus 20 lignes par profil. Worker : il n'écrit pas de test, l'ancien code ignore la table. Export : non exporté.
- **B4. Usages détaillés.** `find_pipelines_using_profile` ne renvoie que des noms. Nouvelle fonction `find_profile_usages(category, profile_id)` qui renvoie, par étape : `pipeline_id`, nom du pipeline, `step_key`, libellé de l'étape, `is_active`, `next_run_at`. Elle couvre aussi `oracle_profile_id` des étapes Sqoop, que `_on_delete_database` ne vérifie pas aujourd'hui (Questions, point 6). Les fonctions existantes restent.
- **B5. Durée de connexion.** `ConnectionTestResult.duration_ms` existe pour les bases (`core/sql_db.py`) mais `_test_one` la perd. Faire renvoyer `(success, message, duration_ms)` par une nouvelle fonction et garder `_test_one` pour ses appelants.

## Lot C : fonctions nouvelles (« proposé »)
Seul C9 porte la pastille « proposé ». Les autres éléments n'en ont pas sur la maquette mais n'existent pas dans le code (Questions, point 2).

| # | Fonction | Frame | Dépend de |
|---|---|---|---|
| C1 | Liste unique groupée en 3 sections et filtres à gauche : « Toutes », « Par famille » (Bases de données, Fichiers (FTP, SFTP), E-mail (SMTP), Big Data (SSH, Kerberos, sudo)) avec compteurs et compte d'échecs, « Par état » (En échec, Jamais testées, Non testées depuis 30 j, Inutilisées) | Connexions | B2, A6 ; question 1 |
| C2 | Bouton « Tester » par ligne, résultat enregistré, ligne mise à jour sans recharger la vue | Connexions | `_test_one`, B3 |
| C3 | « utilisée à 18:00 » sous « Jamais testée » : prochaine exécution d'un pipeline qui l'utilise | Connexions | B4 |
| C4 | Panneau latéral de détail (560 px, Échap) : bandeau « Jamais testée » ou échec avec « Tester maintenant », paramètres en lecture (mot de passe jamais affiché), « Utilisée par N pipelines » avec étape et prochaine exécution, flèche vers `open_atelier(pipeline_id, highlight_step_key)`, « Historique des tests », pied « Modifier », « Dupliquer », « Supprimer » | Connexions-detail | B3, B4, composant Panneau latéral |
| C5 | « Dupliquer » une connexion : copie avec nouveau `uuid`, nom suffixé « (copie) » comme `duplicate_sql_query`, mot de passe recopié chiffré sans passer par l'écran | Connexions-detail | nouvelles fonctions `duplicate_*_profile` |
| C6 | Bouton unique « + Nouvelle connexion » et modale de choix à 9 cartes (titre, description, étapes qui s'en servent) qui ouvre le dialogue existant du type choisi ; remplace les 6 boutons « Nouveau profil » | Connexions-nouvelle | `DbTypeChooserDialog`, dialogues existants |
| C7 | Phrase d'interprétation sous l'erreur (« L'hôte répond : c'est l'identifiant ou le mot de passe. ») tirée d'une table de motifs d'erreur connus ; rien si aucun motif ne correspond | Connexions-formulaire | aucune |
| C8 | Bilan lancé à l'ouverture, barre de progression « 7/12 », compteurs « 5 OK » et « 2 échecs », états « en test » et « en attente », ordre qui teste un bastion avant ses rebonds ; Élévation testée via son SSH (« après Edge Hadoop ») ; pied « 2 échecs touchent 3 pipelines : … » | Connexions-sante | B4, B5 ; question 3 |
| C9 | « Remplacer puis supprimer » : liste « Choisir une connexion SFTP… » limitée au même type, réécrit la clé de profil dans `config_json` des étapes concernées, journalise par `log_audit_event` pour chaque pipeline, puis supprime | Connexions-suppression | B4 |

## Hors périmètre
- La barre de navigation de gauche et la couleur des familles d'étapes (lot 0).
- Les noms, hôtes, heures et compteurs des maquettes : ce sont des exemples.
- L'option SSL du SMTP citée dans la carte « SMTP » de Connexions-nouvelle : le code ne connaît que STARTTLS (question 5).
- L'export et l'import des profils dans les fichiers `.dspipeline`, sauf décision sur B1.

## Critères d'acceptation
- [ ] Capture « Connexions » à 1440×900 avec une base de test contenant les 7 types : chaque profil apparaît dans son groupe, avec type, cible, utilisateur, statut et usage.
- [ ] Les 7 formulaires s'ouvrent depuis la vue, en création et en modification, avec tous les champs listés dans « À garder tel quel » (test par dialogue).
- [ ] Un profil créé puis modifié avec le mot de passe vide garde son mot de passe : `crypto.decrypt` renvoie l'ancien (test).
- [ ] Aucun mot de passe en clair dans la vue, le panneau, les modales ni la table `profile_test_results` : test qui cherche le mot de passe saisi dans le texte de tous les widgets et dans la base.
- [ ] Un profil testé il y a plus de 30 jours, base de données comprise, s'affiche « il y a N jours · à retester » et estompé (test).
- [ ] Un test enregistré à 05:00 UTC s'affiche 07:00 avec `Europe/Paris` en été dans « Dernier test » (test).
- [ ] « Utilisée par » donne le même compte que `find_pipelines_using_profile` ou `find_pipelines_using_db_profile` (test).
- [ ] Capture « Connexions-formulaire » : test en échec affiché en bandeau avec heure et message ; aucun enregistrement du profil tant que « Enregistrer » n'est pas cliqué (test).
- [ ] Capture « Connexions-sante » en cours de test ; Kerberos affiché « non testable ici » et jamais compté en échec (test existant `test_connection_health.py` vert).
- [ ] Capture « Connexions-suppression » ; supprimer un SSH utilisé comme bastion remet `jump_via_id` à vide chez les profils qui l'utilisaient (test).
- [ ] Recherche « partner » : seules les lignes dont le nom, l'hôte ou l'utilisateur contient le texte restent visibles (test).
- [ ] État vide d'un groupe : texte actuel affiché (test `test_onboarding_empty_states.py` vert).
- [ ] Une base 0.45.0 s'ouvre après la migration B1 et B3 ; un ancien worker démarre sur la base migrée (test sur base copiée).
- [ ] Lot C, si retenu : capture « Connexions-detail » et « Connexions-nouvelle » ; C9 laisse chaque étape pointer vers la nouvelle connexion et écrit une ligne de journal par pipeline (test).

## Questions ouvertes
1. **Onglets ou liste unique.** La maquette remplace les 3 onglets par une liste en 3 sections et un filtre. `test_connections_view_has_three_tabs_grouped_by_usage` lit `view.tabs`. Garder les onglets en Lot A, ou accepter de réécrire ce test en Lot C ? Le filtre « Par famille » a 4 entrées alors que la liste a 3 sections : confirmer.
2. **Éléments sans pastille mais absents du code** : filtres de gauche, bouton « Tester » par ligne, « utilisée à 18:00 », panneau de détail, « Dupliquer », modale de choix à 9 types, phrase d'interprétation d'erreur, progression et ordre du bilan, pied « 2 échecs touchent 3 pipelines » (pourtant listé comme proposition dans `manquements.md`), « testé via Edge Hadoop ». Ils sont classés en Lot B ou C. À confirmer.
3. **Élévation dans le bilan.** `_collect_profiles` ignore les profils d'élévation ; la maquette les montre « en attente, après Edge Hadoop ». Kerberos et Élévation ne mémorisent pas le SSH utilisé pour leur test. Tester via le dernier SSH utilisé (colonne `via_ssh_profile_id` de B3) ou laisser « non testable ici » ?
4. **Dossier distant FTP.** L'enregistrer (B1, avec changement de format d'export et règle « chaque étape peut le remplacer » dans `core/ftp.py`) ou retirer le champ mort du formulaire ?
5. **SMTP SSL.** La carte SMTP dit « STARTTLS ou SSL » ; `SmtpProfile` n'a que `use_tls`. Retirer « ou SSL » du texte ?
6. **Oracle utilisé par Sqoop.** `_on_delete_database` ne cherche que `profile_id` et `db_type` ; une étape Sqoop qui référence le profil par `oracle_profile_id` n'est pas signalée. Corriger dans ce lot (B4) ou à part ?
7. **Test en modification.** Le résultat d'un test fait avec des valeurs non enregistrées est inscrit sur le profil enregistré. Garder ce comportement, ou n'enregistrer que si les valeurs testées sont celles en base ?
8. **Couleurs sans clé.** Le fond de section `#191714` et la couleur `#a58cf0` des liens « via Bastion » ne sont pas dans `COLORS`. Ajouter des clés ou se rabattre sur `bg_panel` et `signal_pale` ?
