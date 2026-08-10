"""
DataScheduler — ui/help/content.py
Contenu de la section Aide (rubriques pédagogiques pour l'autonomie de l'utilisateur final).
Embarqué en constantes Python plutôt que chargé depuis des fichiers .md à l'exécution — évite
tout problème de résolution de chemin une fois l'app figée en .exe (sys._MEIPASS), reste
versionnable/diffable normalement, et testable par simple import.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTopic:
    key: str
    title: str
    icon: str
    markdown: str


HELP_TOPICS: list[HelpTopic] = [
    HelpTopic(
        key="overview",
        title="Vue d'ensemble",
        icon="fa5s.info-circle",
        markdown="""# Vue d'ensemble

DataScheduler orchestre des **pipelines de données planifiés** : extraire depuis une base de
données ou un serveur FTP, transformer via un script, charger vers une autre base ou diffuser un
fichier, puis notifier par email si besoin — le tout automatiquement, à l'heure que vous choisissez.

## Les 6 sections de l'application

- **Dashboard** — vue d'ensemble : pipelines actifs, succès/échecs récents, activité des 30
  derniers jours.
- **Pipelines** — créer, modifier, planifier, exécuter manuellement et exporter/importer vos
  pipelines.
- **Connexions** — les profils réutilisables (Oracle, autres bases de données, FTP/SFTP, SMTP)
  que vos pipelines utilisent.
- **Requêtes SQL** — vos requêtes enregistrées, réutilisables dans plusieurs pipelines.
- **Historique** — le journal complet de chaque exécution, plus le journal des modifications.
- **Aide** — vous y êtes.

Chaque pipeline est une suite d'**étapes** (voir la rubrique *Glossaire des types d'étapes*)
exécutées dans l'ordre — ou selon un graphe de dépendances si vous utilisez l'éditeur graphique.
""",
    ),
    HelpTopic(
        key="first-pipeline",
        title="Créer votre premier pipeline",
        icon="fa5s.play-circle",
        markdown="""# Créer et exécuter votre premier pipeline

## 1. Préparer vos connexions

Avant de créer un pipeline, créez les profils dont il aura besoin dans **Connexions** : un profil
Oracle/base de données pour vos requêtes, un profil FTP si vous transférez des fichiers, un profil
SMTP si vous voulez être notifié par email. Utilisez le bouton **Tester** avant d'enregistrer.

## 2. Créer le pipeline

Dans **Pipelines**, cliquez sur **Nouveau pipeline**. Donnez-lui un nom clair, une description, et
choisissez sa planification (fréquence, heure). Vous pourrez la modifier plus tard.

## 3. Ajouter des étapes

Ouvrez l'éditeur (bouton **Modifier**) et ajoutez vos étapes une par une — voir *Glossaire des
types d'étapes* pour choisir le bon type. Chaque étape se configure dans son propre dialogue :
champs requis marqués d'un `*`, un aperçu des jetons disponibles (`{yyyy}`, `{output_file}`…) est
toujours affiché sous les champs concernés.

Pour des pipelines avec du branchement ou plusieurs sources/destinations en parallèle, utilisez
l'**Éditeur graphique** (icône dédiée sur la ligne du pipeline) plutôt que la liste linéaire.

## 4. Tester avant d'activer

Avant de compter sur la planification automatique, utilisez **Exécuter** pour lancer le pipeline
manuellement et vérifier le résultat dans l'**Historique**. Une fois satisfait, activez la
planification depuis la liste des pipelines.

## 5. Suivre les résultats

Le **Dashboard** donne un aperçu rapide (succès/échecs récents, activité). Pour le détail complet
d'une exécution (log, erreur), ouvrez **Historique** et cliquez sur la ligne concernée.
""",
    ),
    HelpTopic(
        key="step-glossary",
        title="Glossaire des types d'étapes",
        icon="fa5s.list-alt",
        markdown="""# Glossaire des types d'étapes

## Extraction & chargement

- **Extraction base de données (`DB_EXTRACT`)** — exécute une requête SQL enregistrée et exporte
  le résultat dans un fichier (CSV par défaut). Publie une sortie nommée personnalisable (champ
  *Nom de sortie*).
- **Téléchargement FTP (`FTP_DOWNLOAD`)** — récupère un fichier depuis un serveur FTP/SFTP. Publie
  également une sortie nommée.
- **Chargement base de données (`DB_LOAD`)** — charge un fichier CSV dans une table. La source du
  fichier vient soit d'une étape précédente (champ *Source*), soit d'un **chemin source
  explicite** si l'étape doit fonctionner seule, sans rien en amont.

## Transfert & diffusion

- **Envoi FTP (`FTP_UPLOAD`)** — dépose un fichier sur un serveur FTP/SFTP. Accepte lui aussi un
  chemin source explicite.
- **Copie locale (`LOCAL_COPY`)** — copie un fichier vers un dossier local ou réseau (ex : un
  partage sur le réseau interne).
- **Compression (`COMPRESS`)** — compresse un fichier en archive ZIP, par exemple avant un envoi
  email ou FTP limité en taille. Même souplesse de source que les autres étapes de ce groupe :
  étape précédente par défaut, *Source* ciblée explicitement, ou **chemin source explicite** si
  l'étape doit fonctionner seule. Le nom de l'archive est personnalisable (jetons acceptés) —
  c'est ce nom qui apparaît comme nom de pièce jointe si l'archive est ensuite envoyée par email.

## Exécution & scripts

- **Exécution SQL (`DB_EXECUTE`)** — exécute une requête ou une procédure stockée sans forcément
  produire de fichier (ex : rafraîchir une vue matérialisée).
- **Script Python (`PYTHON_SCRIPT`)** — lance un script externe avec des arguments personnalisés.
  Le champ *Exécutable Python* est obligatoire : il doit pointer vers le `python.exe` du projet
  concerné (son propre venv/conda), jamais vers DataScheduler — l'application n'a pas
  d'interpréteur Python "par défaut" utilisable pour ça. Chaque étape peut viser un environnement
  différent si vos scripts viennent de projets distincts. Peut lire/écrire le contexte du
  pipeline via un contrat JSON optionnel (voir *Jetons et artefacts*).
- **Spark SQL (`SPARK_SQL`)** — exécute une requête sur un cluster Hadoop via un nœud edge :
  connexion SSH, authentification Kerberos, puis exécution de la requête. Case *Récupérer le
  résultat* pour choisir entre une exécution simple (ex : `INSERT`, rafraîchissement de cache)
  et un résultat rapatrié en fichier. `spark-sql` ne produit qu'un texte brut tabulé — DataScheduler
  le remet en forme en CSV véritable, avec les mêmes réglages que l'étape Extraction base de
  données (séparateur, encodage, guillemets), en-tête de colonnes toujours inclus. Nécessite un
  profil SSH et un profil Kerberos, configurés dans **Connexions**.
- **Export Sqoop (`SQOOP_EXPORT`)** — exporte une table Hive/HCatalog vers Oracle via `sqoop
  export`, sur un nœud edge. Les identifiants Oracle viennent d'un profil existant
  (**Connexions**) — jamais saisis en clair dans l'étape, et le mot de passe n'apparaît jamais
  dans les journaux d'exécution. Base, table HCatalog source et table Oracle cible acceptent les
  jetons (`{yyyy}`, `{MM}`...) pour les tables partitionnées par date. Nécessite un profil SSH et
  un profil Oracle ; deux mécanismes d'authentification distincts et **facultatifs**, à choisir
  selon votre équipe (l'un, l'autre, les deux, ou aucun) : un profil **Kerberos** (kinit, comme
  Spark SQL) et/ou un profil **d'élévation** (`sudo su` vers un compte technique partagé, ex :
  « nifi » — l'élévation, si configurée, précède toujours le kinit).

## Notification & intégration

- **Notification email (`EMAIL_NOTIFY`)** — envoie un email (sujet et corps personnalisables, avec
  jetons), peut joindre le fichier produit par une étape précédente. Une taille max. de pièce
  jointe optionnelle protège des rejets par un serveur mail d'entreprise : au-delà, le pipeline
  échoue proprement (par défaut) ou l'envoi continue sans pièce jointe, selon le réglage choisi.
  Voir aussi l'étape Compression (`COMPRESS`) pour réduire la taille du fichier en amont.
- **Requête HTTP (`HTTP_REQUEST`)** — appelle une URL (webhook, API interne…).

## Contrôle de flux

- **Condition (`CONDITION`)** — disponible uniquement dans l'**éditeur graphique**. Évalue une
  expression simple (ex : `rows_count > 0`, `artifact:rapport != ""`) et oriente l'exécution vers
  l'une de ses deux sorties (`true` / `false`) selon le résultat.
""",
    ),
    HelpTopic(
        key="tokens",
        title="Jetons et artefacts",
        icon="fa5s.hashtag",
        markdown="""# Jetons et artefacts

Les jetons sont des espaces réservés `{...}` que vous pouvez utiliser dans la plupart des champs
texte des étapes (chemins de fichiers, arguments de script, sujet/corps d'email…). Ils sont
remplacés automatiquement au moment de l'exécution.

## Jetons de date/heure

`{yyyy}` `{yy}` `{MM}` `{dd}` `{HH}` `{mm}` `{ss}` `{yyyyMMdd}` `{yyyyMMddHHmm}` — date et heure du
moment de l'exécution. Exemple : `export_{yyyyMMdd}.csv` devient `export_20260801.csv`.

## Jetons de contexte

- `{output_file}` — le chemin du fichier produit par l'étape précédente (ou par la *Source*
  choisie explicitement).
- `{rows_count}` — le nombre de lignes traitées par l'étape précédente.
- `{error}` / `{failed_step}` — utiles dans une étape de notification email marquée **toujours
  exécuter**, pour signaler ce qui a échoué et où.

## Artefacts nommés — pour aller plus loin

Par défaut, chaque étape qui produit un fichier le publie sous le nom générique `output_file` —
l'étape suivante le récupère automatiquement. Si votre pipeline a **plusieurs** sources en
parallèle, donnez à chacune un **nom de sortie** distinct (champ visible dans les dialogues
d'étapes productrices), puis référencez-le où vous voulez avec `{artifact:nom}`. Le bouton
**+ Artefact** à côté des champs concernés insère automatiquement le bon jeton pour vous — pas
besoin de retenir les noms par cœur.

> Un `{artifact:nom}` qui ne correspond à aucune sortie publiée avant cette étape reste affiché
> tel quel dans le résultat, sans faire échouer le pipeline — un signal visible que quelque chose
> ne correspond pas (nom mal orthographié, étape déplacée après plutôt qu'avant…).

## Scripts Python — contrat JSON optionnel

Un script peut aussi lire/écrire directement les artefacts du pipeline via deux jetons réservés à
l'étape Script Python : `{ds_context_in}` (chemin d'un fichier JSON à lire, contenant les artefacts
déjà produits) et `{ds_context_out}` (chemin d'un fichier JSON à écrire, pour publier de nouveaux
artefacts). Facultatif — un script qui ne les référence pas fonctionne exactement comme avant.
""",
    ),
    HelpTopic(
        key="connections",
        title="Connexions (profils)",
        icon="fa5s.plug",
        markdown="""# Connexions (profils)

Un **profil** regroupe les informations de connexion à un système externe, réutilisable par
plusieurs pipelines. Six types :

- **Oracle** — hôte, port, service/SID, identifiants.
- **Base de données** (autres SGBD supportés) — même principe, avec le type de base à choisir.
- **FTP/SFTP** — hôte, port, protocole, identifiants, dossier de départ.
- **SMTP** — pour l'envoi d'emails (notifications, digest) : serveur, port, adresse d'expédition.
- **SSH** — connexion à un nœud edge/master d'un cluster Hadoop (étape Spark SQL) : hôte, port,
  identifiants.
- **Kerberos** — identité nominative pour l'authentification `kinit` (étape Spark SQL) :
  principal, mot de passe. Un ticket Kerberos ne se teste pas seul — le test depuis ce profil
  demande de choisir un profil SSH sur lequel lancer `kinit`.

## Sécurité des mots de passe

Les mots de passe des profils sont **chiffrés** avant d'être enregistrés en base — ils ne sont
jamais réaffichés en clair, y compris quand vous rouvrez un profil pour le modifier. Le champ mot
de passe apparaît vide à l'édition : laissez-le vide pour conserver le mot de passe déjà
enregistré, ou saisissez-en un nouveau pour le remplacer.

> Le mot de passe d'un profil Kerberos est personnel/nominatif — plus sensible qu'un compte de
> service. Il reste chiffré comme tout autre mot de passe, mais mérite une attention
> particulière si votre organisation a des règles spécifiques sur ce type d'identifiant.

## Tester avant d'enregistrer

Chaque dialogue de profil a un bouton **Tester** — utilisez-le systématiquement avant
d'enregistrer, ça évite de découvrir un problème de connexion seulement au moment où un pipeline
planifié échoue.
""",
    ),
    HelpTopic(
        key="scheduling",
        title="Planification et notifications",
        icon="fa5s.bell",
        markdown="""# Planification et notifications

## Planifier un pipeline

Chaque pipeline a sa propre fréquence (quotidienne, hebdomadaire…) et son heure d'exécution,
définies à la création ou modifiables ensuite. Un pipeline planifié doit être **activé** pour
s'exécuter automatiquement — un pipeline désactivé reste utilisable manuellement (bouton
**Exécuter**) sans jamais se déclencher tout seul.

## Être prévenu des échecs

Deux niveaux, complémentaires :

- **Dashboard** — les exécutions en échec ressortent visuellement (nom en rouge, détail de
  l'erreur au survol) dans la table des dernières exécutions.
- **Digest par email** — depuis le Dashboard, bouton **Notifications** : activez un résumé
  quotidien ou hebdomadaire envoyé par email (profil SMTP + destinataires requis), qui liste les
  succès/échecs de la période. Utile si vous n'ouvrez pas l'application tous les jours.

> Un échec sur un pipeline **planifié** est capturé de la même façon qu'un échec déclenché
> manuellement — vous êtes averti dans les deux cas, pas seulement quand vous lancez le pipeline
> vous-même.
""",
    ),
    HelpTopic(
        key="export-import",
        title="Export, import et sécurité",
        icon="fa5s.file-export",
        markdown="""# Export, import et sécurité

## Exporter un pipeline

Depuis **Pipelines**, bouton **Exporter** sur la ligne du pipeline. Un mot de passe est
**facultatif** :

- Sans mot de passe : les mots de passe des profils utilisés (Oracle, FTP, SMTP…) sont **omis**
  du fichier exporté — pratique pour partager la structure d'un pipeline sans révéler
  d'identifiants ; chacun ressaisit les siens à l'import.
- Avec mot de passe : les mots de passe des profils sont chiffrés dans le fichier `.dspipeline`
  produit ; le reste (hôte, port, nom d'utilisateur…) reste lisible, pour pouvoir inspecter le
  fichier sans le déchiffrer entièrement.

## Importer un pipeline

Bouton **Importer** en haut de la liste des pipelines, sélectionnez un fichier `.dspipeline`. Si
le fichier est protégé par mot de passe, il vous sera demandé — le même mot de passe utilisé à
l'export.

Par défaut, un profil déjà présent (identifié en interne, pas juste par son nom) est **réutilisé**
plutôt que dupliqué ; un pipeline déjà présent est importé comme une **copie renommée**, jamais
écrasé silencieusement. Un écran de révision vous permet de choisir explicitement d'écraser le
pipeline existant, ou de remapper un profil vers un profil local existant plutôt que d'en créer un
nouveau.
""",
    ),
    HelpTopic(
        key="troubleshooting",
        title="Dépannage",
        icon="fa5s.life-ring",
        markdown="""# Dépannage

**« Aucun fichier source disponible »**
L'étape n'a ni *Source* choisie ni *Chemin source explicite*, et aucune étape précédente n'a
produit de fichier. Renseignez l'un des deux (voir *Glossaire des types d'étapes*).

**« Le nom de sortie « X » est utilisé par plusieurs étapes »**
Deux étapes déclarent le même *Nom de sortie* — chaque nom doit être unique dans le pipeline.
Renommez l'une des deux (voir *Jetons et artefacts*).

**Un `{artifact:nom}` apparaît tel quel dans le résultat au lieu d'être remplacé**
Le nom ne correspond à aucune sortie publiée par une étape qui s'exécute *avant* celle-ci —
vérifiez l'orthographe exacte du nom, ou l'ordre des étapes.

**Un pipeline planifié a échoué mais je n'ai rien reçu**
Vérifiez que le digest de notifications est activé (Dashboard → **Notifications**, un profil SMTP
et des destinataires sont requis), ou consultez directement l'**Historique** — chaque exécution y
est enregistrée, notifiée ou non.

**« Mot de passe incorrect » à l'import**
Le fichier `.dspipeline` a été exporté avec un mot de passe — il faut fournir exactement le même
mot de passe pour l'importer.

**Un mot de passe de connexion semble avoir disparu après modification d'un profil**
C'est normal — le champ mot de passe est toujours vide à l'ouverture d'un profil existant (jamais
réaffiché en clair). Laissez-le vide pour conserver l'ancien mot de passe ; ne le remplissez que
pour le changer.
""",
    ),
]
