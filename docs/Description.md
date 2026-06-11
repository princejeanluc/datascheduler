# Description 

## Context

Les utilisateurs se connectent sur une base de données oracle grâce à Taud , effectue une requête qui peut être lourde (soit un temps d'attente important) , ensuite les données sont extraites en format csv puis déposées sur un serveur via le protocol ftp et respectant une nomenclature pour le nom et le chemin de stockage. 


# Problème 

Il est lassant de requêter et de stocker manuellement les données sur un serveur ftp et de le faire de manière répétitive.

# Proposition

Un logiciel qui permet aux utilisateurs de créer des crons (événements périodiques), pour le fetch et le dépot des fichiers

# Contrainte

+ Fait en python 
+ La solution doit être un executable window pour être facilement partagé au personnelle entreprise , une solution web n'est pas envisageable car l'implémentation des solutions entreprise par web est très réglémentés. 

# User Stories 

+ le user doit pouvoir créer  un profil Db (oracle) et  ftp (se qui va le permettre de les selectionner lors de la création de mini pipeline ) 
+ il créera des pipelines cron qu'il nommera.
