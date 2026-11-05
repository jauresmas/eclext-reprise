"""Étape 10 : met en forme le cahier de recette à partir des résultats des tests.

Lit livrables/recette/resultats_tests.json (écrit par pytest) et écrit cahier_recette.md et cahier_recette.xlsx.
Un test relancé plusieurs fois avec des valeurs différentes forme une seule ligne. Les vérifications que seul
un utilisateur peut faire figurent aussi, avec le résultat « non exécuté » : elles restent à dérouler.

    python 10_cahier_recette.py
"""
import datetime as dt
import json
import re

import config
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from outils import curseur, fr, log

RECETTE = config.LIVRABLES / "recette"

SERIES = {
    "T-REP": "Reprise : rien ne se perd entre la source et la base",
    "T-CTR": "Contrôles : les erreurs posées exprès sont retrouvées",
    "T-STR": "Structure : la base refuse ce qui est incohérent",
    "T-ROL": "Comptes et droits : chacun reste dans son périmètre",
    "T-EXP": "Exploitation : signalements et interventions",
    "T-ECL": "Format d'échange : les fichiers livrés, relus sans la base",
    "T-FLX": "Flux : une nouvelle publication, sur une copie de la base",
    "T-APP": "Projets QGIS : rouverts avec le compte de chaque profil",
    "T-IHM": "Fenêtre QGIS : le parcours réel de chaque profil",
    "T-MAN": "Vérifications par un utilisateur",
}

MANUELS = [
    ("T-MAN-01", "Une personne de la collectivité, avec le seul guide, signale une panne depuis la carte"),
    ("T-MAN-02", "Une personne de l'entreprise, avec le seul guide, planifie puis clôt une intervention"),
    ("T-MAN-03", "Un échantillon de points est comparé au terrain : position, type de source, puissance"),
    ("T-MAN-04", "Un gestionnaire confirme ou écarte les correspondances marquées « arbitrage »"),
    ("T-MAN-05", "Une session de formation est déroulée avec le plan proposé, et chronométrée"),
]


def regrouper(resultats):
    """Une ligne par numéro : réussie seulement si tous ses cas ont réussi."""
    lignes = {}
    for r in resultats:
        numero = r["numero"].split(" [")[0]
        ligne = lignes.setdefault(numero, {"numero": numero, "libelle": r["libelle"], "cas": 0, "echecs": 0, "constats": []})
        ligne["cas"] += 1
        ligne["echecs"] += r["resultat"] != "réussi"
        if r["constat"]:
            parametre = re.search(r"\[(.*)\]", r["numero"])
            ligne["constats"].append(f"{parametre.group(1)} : {r['constat']}" if parametre and ligne["cas"] <= 40 else r["constat"])
    for ligne in lignes.values():
        ligne["resultat"] = "réussi" if not ligne["echecs"] else "échoué"
    return sorted(lignes.values(), key=lambda x: (list(SERIES).index(x["numero"][:5]), x["numero"]))


def environnement():
    with curseur() as cur:
        cur.execute("SELECT rtrim(split_part(version(), ' ', 2), ','), postgis_lib_version()")
        postgres, postgis = cur.fetchone()
    return f"PostgreSQL {postgres}, PostGIS {postgis}, QGIS 3.34"


def markdown(lignes, total, echecs, env, jour):
    texte = ["# Cahier de recette", "",
             f"Résultats du {jour}, sur {env}. Le cahier est produit par `scripts/10_cahier_recette.py` à partir des tests "
             "du dossier `tests/` : chaque ligne vient d'un test exécuté, sauf la dernière série, qui reste à dérouler.", "",
             f"**{fr(total)} cas exécutés, {fr(echecs)} en échec.** Les signalements et les interventions testés forment un "
             "jeu d'essai, marqué `jeu_essai = true` en base : les sources ne publient aucun historique de maintenance.", "",
             "| Série | Vérifications | Cas | Réussies | Échouées | Non exécutées |", "|---|---:|---:|---:|---:|---:|"]
    for code, titre in SERIES.items():
        serie = [x for x in lignes if x["numero"].startswith(code)]
        texte.append(f"| {titre} | {len(serie)} | {sum(x['cas'] for x in serie)} | {sum(x['resultat'] == 'réussi' for x in serie)} "
                     f"| {sum(x['resultat'] == 'échoué' for x in serie)} | {sum(x['resultat'] == 'non exécuté' for x in serie)} |")
    for code, titre in SERIES.items():
        texte += ["", f"## {code} : {titre}", "", "| N° | Vérification | Cas | Résultat | Constat |", "|---|---|---:|---|---|"]
        for x in (x for x in lignes if x["numero"].startswith(code)):
            constat = " ; ".join(x["constats"]).replace("|", "/").replace("\n", " ")
            texte.append(f"| {x['numero']} | {x['libelle']} | {x['cas'] or ''} | {x['resultat']} | {constat[:700]} |")
    return "\n".join(texte) + "\n"


def tableur(lignes, chemin):
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Cahier de recette"
    feuille.append(["N°", "Série", "Vérification", "Cas", "Résultat", "Constat"])
    couleurs = {"réussi": "D9EAD3", "échoué": "F4CCCC", "non exécuté": "EEEEEE"}
    for x in lignes:
        feuille.append([x["numero"], SERIES[x["numero"][:5]], x["libelle"], x["cas"] or None, x["resultat"], " ; ".join(x["constats"])[:32000]])
        feuille.cell(feuille.max_row, 5).fill = PatternFill("solid", fgColor=couleurs[x["resultat"]])
    for cellule in feuille[1]:
        cellule.font = Font(bold=True)
    for lettre, largeur in zip("ABCDEF", (11, 42, 64, 6, 13, 90)):
        feuille.column_dimensions[lettre].width = largeur
    for rangee in feuille.iter_rows(min_row=2):
        for cellule in rangee:
            cellule.alignment = Alignment(wrap_text=True, vertical="top")
    feuille.freeze_panes = "A2"
    feuille.auto_filter.ref = feuille.dimensions
    classeur.save(chemin)


if __name__ == "__main__":
    resultats = json.loads((RECETTE / "resultats_tests.json").read_text(encoding="utf-8"))
    lignes = regrouper(resultats) + [{"numero": n, "libelle": l, "cas": 0, "echecs": 0, "constats": [], "resultat": "non exécuté"} for n, l in MANUELS]
    echecs = sum(r["resultat"] != "réussi" for r in resultats)
    jour = dt.date.today().strftime("%d/%m/%Y")
    (RECETTE / "cahier_recette.md").write_text(markdown(lignes, len(resultats), echecs, environnement(), jour), encoding="utf-8")
    tableur(lignes, RECETTE / "cahier_recette.xlsx")
    log(f"Cahier de recette : {fr(len(resultats))} cas, {fr(echecs)} en échec, {len(MANUELS)} vérifications manuelles à dérouler")
