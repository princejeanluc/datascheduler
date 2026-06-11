Architecture fonctionnelle
1. Gestion des connexions
Profil Oracle

L'utilisateur crée un profil :

Nom du profil
Hôte
Port
Service Name / SID
Utilisateur
Mot de passe

Exemple :

ORACLE_PROD
Host : 10.10.1.15
Port : 1521
Service : PROD
User : reporting
Profil FTP

L'utilisateur crée un profil FTP :

Nom du profil
Host
Port
User
Password
FTP ou FTPS

Exemple :

FTP_FINANCE

Host : ftp.company.com
Port : 21
Protocol : FTPS
2. Gestion des requêtes SQL

L'utilisateur peut créer des requêtes réutilisables :

SELECT *
FROM sales
WHERE sale_date >= TRUNC(SYSDATE)-1

Stockage :

REQUETE_VENTES_JOUR

Ainsi plusieurs pipelines pourront utiliser la même requête.

3. Création d'un Pipeline

Exemple :

Pipeline :
EXPORT_VENTES_QUOTIDIEN

Configuration :

Source
Profil Oracle :
ORACLE_PROD

Requête :
REQUETE_VENTES_JOUR
Export
Format :
CSV

Séparateur :
;

Encodage :
UTF-8
Destination
Profil FTP :
FTP_FINANCE
Nommage

L'utilisateur définit un template :

ventes_{yyyyMMdd}.csv

Résultat :

ventes_20260608.csv
Chemin distant

Template :

/export/finance/{yyyy}/{MM}/

Résultat :

/export/finance/2026/06/
4. Planification

L'utilisateur choisit :

Quotidien
Tous les jours à 06:00
Hebdomadaire
Tous les lundis à 08:00
Mensuel
Le 1er du mois

Ou directement :

0 6 * * *

si tu souhaites exposer la syntaxe cron.

5. Monitoring

Chaque exécution génère un log :

08/06/2026 06:00

Pipeline :
EXPORT_VENTES_QUOTIDIEN

Connexion Oracle : OK

Requête exécutée :
2 435 612 lignes

Export CSV : OK

Upload FTP : OK

Durée :
00:08:21
6. Historique

Vue :

Pipeline                    Statut
-----------------------------------------
EXPORT_VENTES_QUOTIDIEN     SUCCESS
EXPORT_CLIENTS              FAILED
EXPORT_STOCKS               SUCCESS

Avec possibilité d'ouvrir le détail.