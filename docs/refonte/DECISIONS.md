# Décisions

Les fiches d'écran listent des questions ouvertes. Ce fichier les tranche. Chaque décision a une réponse par défaut : Claude Code l'applique tant qu'elle n'est pas marquée autrement. Quand tu changes une réponse, modifie la ligne et passe son état à « tranché ».

États : **à trancher** (le lot concerné ne commence pas avant), **par défaut** (appliqué sauf avis contraire), **tranché**.

## Décisions produit

| # | Question | Réponse par défaut | État |
|---|---|---|---|
| P1 | Les maquettes Atelier, Aujourd'hui et Pipelines, dessinées avant la règle des pastilles, montrent beaucoup d'éléments absents du code sans pastille « proposé ». Connexions, Requêtes SQL et Historique en ont quelques-uns. Sont-ils à livrer ? | Oui. Pour l'Atelier spécifiquement, le Lot C (C7, C9) démarre dès maintenant, en avance de phase sur le Lot A des autres écrans — écran prioritaire, demande explicite de l'utilisateur à partir des maquettes Atelier-ajout et Atelier-echec. Les autres écrans restent à « après leur Lot A » | tranché |
| P2 | Atelier : les maquettes montrent « enregistré automatiquement » et plus de bouton d'enregistrement ; le code n'a pas de sauvegarde automatique, par choix | Garder les deux boutons. La sauvegarde automatique et le brouillon (C6, table `pipeline_drafts`) forment un lot à part, décidé plus tard | à trancher |
| P3 | Atelier : la barre des pipelines à gauche n'apparaît sur aucune maquette | La garder, repliable comme aujourd'hui | par défaut |
| P4 | Supprimer un pipeline efface ses runs (`cascade="all, delete-orphan"`), alors que les maquettes Pipelines et Historique disent « exécutions conservées » | Garder le comportement, corriger le texte : « Les N exécutions de l'historique seront supprimées. » | à trancher |
| P5 | Connexions : la maquette remplace les 3 onglets par une liste unique en 3 sections | Lot A garde les onglets ; la liste unique passe en lot C, avec réécriture du test des onglets | par défaut |
| P6 | Requêtes SQL : la maquette remplace « Profil » par « Tester sur » ; `oracle_profile_id` filtre pourtant les requêtes dans les dialogues d'étape Oracle | Garder « Profil » ; « Tester sur » n'arrive qu'avec l'aperçu des résultats (C1) | par défaut |
| P7 | Le premier écran s'appelle « Dashboard » dans la navigation et « Aujourd'hui » sur les maquettes | Renommer en « Aujourd'hui » partout (navigation, palette, aide) | à trancher |
| P8 | Pipelines : pendant un run, le premier bouton de la ligne arrête le run sur la maquette ; le code en lance un second si `prevent_overlap` est désactivé | Arrêter. Lancer un second run reste possible depuis le menu ⋯ | à trancher |
| P9 | « Tout exécuter » et le rattrapage lancent aujourd'hui un pipeline enfant deux fois (directement, puis déclenché par son parent) | Lancer dans l'ordre des dépendances et ne plus lancer l'enfant directement | à trancher |
| P10 | Pipelines : double-clic sur une ligne. Maquette : ouvre l'Atelier. Code : ouvre le détail du pipeline | Garder le code jusqu'à ce que l'Historique filtré par pipeline remplace le dialogue de détail ; ensuite, ouvrir l'Atelier | par défaut |
| P11 | Atelier : la Grammaire remplace l'icône du type d'étape par un point de couleur de famille | Garder le point de couleur de famille, comme livré (lot Grammaire, PR #85). L'icône de type n'est pas réintroduite | tranché |
| P12 | Aperçu des résultats SQL sur SQL Server, qui n'a pas de transaction en lecture seule | Refus par analyse de la requête et `rollback` systématique, plus un avertissement d'utiliser un compte en lecture seule | par défaut |

## Règles techniques par défaut

| # | Sujet | Règle |
|---|---|---|
| T1 | Tests qui figent un texte ou une colonne que la fiche change | Mettre à jour l'assertion dans le même lot, et le dire dans la note d'impact. Ne jamais retirer un test de comportement |
| T2 | Couleurs vues dans une maquette sans clé dans `COLORS` | Ajouter une clé nommée selon l'usage (liste dans `FONDATIONS.md`), jamais de valeur en dur |
| T3 | Heures écrites en UTC dans `log_text` (`[HH:MM:SS]`) | Les convertir à l'affichage avec la date de début du run ; l'écriture ne change pas |
| T4 | Heure des jetons de date : `resolve_tokens` utilise l'heure de la machine, pas le fuseau réglé | Afficher ce que l'exécution fera vraiment (heure de la machine). L'écart est noté dans `manquements.md`, à corriger à part |
| T5 | Défauts trouvés en lisant le code (section « Correctifs » de `LOTS.md`) | Les corriger dans de petits lots dédiés, avant les lots A, chacun avec son test |
| T6 | Ouvrir un élément d'une liste | Simple clic : sélectionne. Double-clic ou Entrée : ouvre, comme aujourd'hui |
| T7 | Élément visible sur une maquette, absent du code, et non listé dans la fiche | Ne pas le faire. Le signaler dans la PR, section « Hors périmètre repéré » |
| T8 | Question ouverte d'une fiche non reprise ici | Appliquer la recommandation écrite dans la fiche s'il y en a une ; sinon s'arrêter et demander |

## Questions mineures déjà tranchées par défaut

- Historique : ajouter un segment « Réussis » au filtre, puisque le Dashboard ouvre l'Historique filtré sur les réussites.
- Connexions : retirer « ou SSL » de la carte SMTP, le code ne gère que STARTTLS.
- Connexions : un test fait sur des valeurs non enregistrées n'inscrit son résultat que si ces valeurs sont celles en base.
- Pipelines : l'export ne contient pas les déclenchements ; corriger le texte de la fenêtre d'export plutôt que changer le format.
- Pipelines : lignes inactives ; garder le comportement du code (on peut lancer, ouvrir et réactiver), seulement estomper la ligne.
- Atelier : « Abandonner après » est le délai par tentative (`timeout_s`) ; le libellé devient « Délai par tentative ».
