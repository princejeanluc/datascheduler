"""
DataScheduler — ui/step_editor/python_script_template.py
Modèle de script pédagogique, téléchargeable depuis le dialogue de configuration d'une étape
PYTHON_SCRIPT — pour quelqu'un qui découvre l'application et doit y brancher son propre script,
sans avoir à deviner le contrat (arguments, code de sortie, échange de données avec les autres
étapes) en lisant le code source de DataScheduler.
"""

PYTHON_SCRIPT_TEMPLATE = '''"""
Modèle de script pour une étape "Script Python" DataScheduler.

Ce script tourne dans SON PROPRE processus Python — indépendant de DataScheduler (son propre
interpréteur, ses propres dépendances). Aucun import de DataScheduler n'est possible ni requis :
ce fichier n'a besoin que de la bibliothèque standard pour fonctionner tel quel.

Comment DataScheduler communique avec ce script :
  - Arguments (argv) : configurés UN PAR LIGNE dans le champ "Arguments" de l'étape. Chaque ligne
    devient un élément d'argv, tel quel — pas d'interprétation façon shell (pas de découpage sur
    les espaces, pas de guillemets à gérer).
  - Code de sortie : 0 = succès, tout code non nul = échec de l'étape. C'est le SEUL signal de
    réussite/échec que DataScheduler regarde.
  - stdout / stderr : capturés et journalisés dans l'historique d'exécution, utiles pour le
    débogage. La dernière ligne de stderr est reprise dans le message d'erreur si le script
    échoue.
  - Champ "Exécutable Python" de l'étape : DOIT pointer vers le python.exe de ce script (son
    propre venv/conda) — jamais laissé vide, jamais celui de DataScheduler.

Échange de données avec les autres étapes du pipeline (facultatif) — voir les jetons
{ds_context_in} / {ds_context_out} du champ "Arguments" :
  - {ds_context_in}  : si ajouté, ce script reçoit en argument le chemin d'un fichier JSON à LIRE,
    contenant ce que les étapes précédentes ont déjà produit.
  - {ds_context_out} : si ajouté, ce script reçoit en argument le chemin d'un fichier JSON à
    ÉCRIRE (facultatif) pour publier un résultat vers les étapes suivantes.

Trois cas d'usage illustrés ci-dessous, chacun dans sa propre section — gardez seulement celui
qui vous concerne, supprimez le reste.
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Exemple de script DataScheduler")
    # Vos propres arguments métier, tels que configurés dans le champ "Arguments" de l'étape.
    # Exemple : {yyyyMMdd} est résolu par DataScheduler avant d'être passé au script.
    parser.add_argument("--date", help="Exemple d'argument métier (ex : {yyyyMMdd})")
    # Les deux arguments suivants ne servent que si {ds_context_in}/{ds_context_out} ont été
    # ajoutés au champ "Arguments" de l'étape — supprimez-les sinon.
    parser.add_argument("--context-in", dest="context_in", default=None)
    parser.add_argument("--context-out", dest="context_out", default=None)
    args = parser.parse_args()

    print(f"Démarrage du traitement (date={args.date})")

    # ── CAS 1 : script autonome, sans lien avec les autres étapes du pipeline ──────────
    # Rien de plus à faire : votre logique métier ici, puis sortez avec le code 0 en cas de
    # succès (voir sys.exit(0) en bas de fichier).

    # ── CAS 2 : lire ce que les étapes précédentes ont produit ─────────────────────────
    if args.context_in:
        with open(args.context_in, "r", encoding="utf-8") as f:
            context = json.load(f)
        # context["artifacts"] : dict {nom_publié: chemin_fichier} — "output_file" est le nom
        # par défaut utilisé par la plupart des étapes productrices (extraction DB, FTP...).
        input_file = context["artifacts"].get("output_file")
        print(f"Fichier reçu de l'étape précédente : {input_file}")
        # ... votre traitement de input_file ici ...

    # ── CAS 3 : publier un résultat pour les étapes suivantes ──────────────────────────
    if args.context_out:
        result_path = "C:/chemin/vers/mon_resultat.csv"  # ex : généré par ce script
        with open(args.context_out, "w", encoding="utf-8") as f:
            json.dump({"artifacts": {"output_file": result_path}}, f)
        print(f"Résultat publié pour l'étape suivante : {result_path}")

    print("Traitement terminé avec succès.")
    sys.exit(0)  # tout code non nul est traité comme un échec par DataScheduler


if __name__ == "__main__":
    main()
'''
