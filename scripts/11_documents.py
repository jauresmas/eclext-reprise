"""Étape 11 : imprime en PDF les guides, le plan de formation et le rapport de reprise.

Les modèles sont dans docs/modeles ; les chiffres du rapport sont lus dans la base et les résultats de contrôle.
Impression avec Edge, par Playwright.

    python 11_documents.py
"""
import datetime as dt
import json

import config
import jinja2
from outils import curseur, fr, log
from playwright.sync_api import sync_playwright

MODELES = config.DOCS / "modeles"
DOCUMENTS = ["guide_collectivite", "guide_entreprise", "memo_administrateur", "plan_formation", "rapport_reprise"]
NOMS = {"SDE18": "Cher (SDE18)", "NANTES": "Nantes Métropole", "LOIRE": "Publication Loire"}
NOMS_SOURCES = {"sde18": NOMS["SDE18"], "nantes": NOMS["NANTES"], "loire": NOMS["LOIRE"]}
ZONES = ["SDE18", "NANTES", "LOIRE"]
OBLIGATOIRES = ["statut", "eclairagePublic", "usage", "typeSource", "structure", "support", "temperatureCouleur", "puissance",
                "valideDe", "extinctionNuit", "estAdaptatif"]


def rangees(cur, requete, *parametres):
    cur.execute(requete, parametres or None)
    colonnes = [d[0] for d in cur.description]
    return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


def donnees_rapport():
    d = {"zones": ZONES, "noms": NOMS, "noms_sources": NOMS_SOURCES, "jour": dt.date.today().strftime("%d/%m/%Y")}
    with curseur() as cur:
        d["bilan"] = sorted(rangees(cur, "SELECT * FROM controle.bilan_reprise"), key=lambda b: ZONES.index(b["gestionnaire"]))
        d["total"] = {"lignes": sum(b["lignes_source"] for b in d["bilan"]), "points": sum(b["points_repris"] for b in d["bilan"]),
                      "supports": sum(b["supports_repris"] for b in d["bilan"]), "fusionnees": sum(b["lignes_fusionnees"] for b in d["bilan"]),
                      "ecartees": sum(b["lignes_ecartees"] for b in d["bilan"]), "ecart": sum(abs(b["ecart"]) for b in d["bilan"])}
        cur.execute("SELECT count(*), count(*) FILTER (WHERE position_estimee) FROM metier.armoire WHERE retire_le IS NULL")
        d["armoires"], d["armoires_estimees"] = cur.fetchone()
        cur.execute("SELECT count(*) FROM controle.ecart")
        d["nb_ecarts"] = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT code), sum(nb_ecarts) FILTER (WHERE gravite = 'bloquante') FROM controle.bilan_regle WHERE nb_ecarts > 0")
        d["nb_regles"], d["nb_bloquants"] = cur.fetchone()
        cur.execute("SELECT count(*) FROM controle.regle")
        d["nb_regles_definies"] = cur.fetchone()[0]
        cur.execute("SELECT sum(points_conformes) FROM controle.conformite_source")
        d["conformes"] = cur.fetchone()[0]

        cur.execute("""SELECT count(*),
                              count(*) FILTER (WHERE EXISTS (SELECT 1 FROM ref.commune c WHERE c.departement = '74' AND ST_Within(p.geom, c.geom))),
                              count(*) FILTER (WHERE EXISTS (SELECT 1 FROM ref.commune c WHERE c.departement = '42' AND ST_Within(p.geom, c.geom))),
                              count(DISTINCT p.insee)
                       FROM metier.point_lumineux p JOIN metier.gestionnaire g ON g.id = p.gestionnaire_id WHERE g.code = 'LOIRE' AND p.retire_le IS NULL""")
        d["loire"] = dict(zip(("points", "dans_74", "dans_42", "communes"), cur.fetchone()))

        taux = rangees(cur, "SELECT gestionnaire, attribut, taux_renseigne, origine FROM controle.conformite_attribut WHERE obligatoire")
        d["attributs"] = []
        for attribut in OBLIGATOIRES:
            ligne = {"nom": attribut}
            for t in (t for t in taux if t["attribut"] == attribut):
                ligne[t["gestionnaire"]] = float(t["taux_renseigne"] or 0)
                ligne[t["gestionnaire"] + "_hypothese"] = t["origine"] == "hypothese"
            d["attributs"].append(ligne)
        d["absents_sde18"] = sum(1 for a in d["attributs"] if a["SDE18"] == 0)
        cur.execute("""SELECT round(avg(n), 3) FROM (SELECT count(*) AS n FROM metier.point_lumineux p JOIN metier.gestionnaire g ON g.id = p.gestionnaire_id
                       WHERE g.code = 'NANTES' AND p.retire_le IS NULL GROUP BY p.support_id) s""")
        d["foyers_par_support"] = str(cur.fetchone()[0]).replace(".", ",")

        rap = {r["statut"]: r for r in rangees(cur, """SELECT statut, count(*) AS n, count(distance_m) AS mesures, percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m) AS mediane,
                                                              max(distance_m) AS maxi
                                                       FROM controle.rapprochement GROUP BY statut""")}
        par_regle = {r["code"]: r["n"] for r in rangees(cur, "SELECT regle AS code, count(*) AS n FROM controle.ecart WHERE regle LIKE 'RAP_%' GROUP BY 1")}
        cur.execute("SELECT count(*) FROM src.ccf c JOIN flux.lot l ON l.id = c.lot_id AND l.courant WHERE nullif(c.x, '') IS NULL OR nullif(c.y, '') IS NULL")
        d["rap"] = {"apparie": rap["apparie"]["n"], "mesures": rap["apparie"]["mesures"], "mediane": float(rap["apparie"]["mediane"]), "maxi": float(rap["apparie"]["maxi"]), "plus_de_5m": par_regle["RAP_04"],
                    "recode": rap["recode_probable"]["n"], "absent_syndicat": rap["absent_syndicat"]["n"], "absent_ccf": rap["absent_ccf"]["n"],
                    "proprietaire": par_regle["RAP_05"], "sans_position": cur.fetchone()[0]}

        regles = {}
        for r in rangees(cur, "SELECT code, libelle, gravite, gestionnaire, nb_ecarts FROM controle.bilan_regle WHERE nb_ecarts > 0 AND code NOT LIKE 'RAP_%'"):
            regles.setdefault(r["code"], {"code": r["code"], "libelle": r["libelle"], "gravite": r["gravite"]})[r["gestionnaire"]] = r["nb_ecarts"]
        ordre = ["bloquante", "majeure", "mineure", "information"]
        d["regles"] = sorted(regles.values(), key=lambda r: (ordre.index(r["gravite"]), r["code"]))
        for regle in d["regles"]:
            for zone in ZONES:
                regle.setdefault(zone, 0)

        certitudes = dict(rangees_couples(cur, "SELECT certitude, count(*) FROM ref.correspondance GROUP BY 1"))
        d["corr"] = {"total": sum(certitudes.values()), **certitudes}
        d["arbitrages"] = rangees(cur, """SELECT source, champ_source AS champ, valeur_source AS valeur, valeur_cible AS cible, commentaire
                                          FROM ref.correspondance WHERE certitude = 'arbitrage' ORDER BY 1, 2, 3""")
        collectes = dict(rangees_couples(cur, "SELECT source, date_collecte FROM flux.lot WHERE courant"))
    d["sources"] = [{"titre": s["titre"], "producteur": s["producteur"], "date": dt.datetime.strptime(collectes[cle], "%Y%m%d").strftime("%d/%m/%Y")}
                    for cle, s in config.SOURCES_OUVERTES.items()]

    d["recette"] = []
    for zone in ZONES:
        r = json.loads((config.LIVRABLES / "recette_geo" / zone / f"recette_{zone}_V01_resultats.json").read_text(encoding="utf-8"))["recevabilite"]
        d["recette"].append({"zone": zone, "objets": r["objets"], "bloquante": r["bloquante"], "majeure": r["majeure"], "pour_mille": r["majeures_pour_mille"], "statut": r["statut"]})
    modele = json.loads((config.LIVRABLES / "recette" / "croisement_modele.json").read_text(encoding="utf-8"))
    d["modele"] = dict(modele, total_differences=sum(modele["differences"].values()))
    return d


def rangees_couples(cur, requete):
    cur.execute(requete)
    return cur.fetchall()


def imprimer():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(MODELES), autoescape=True)
    env.filters["fr"] = fr
    env.filters["fr1"] = lambda v: fr(v, 1)
    contexte = donnees_rapport()
    pied = ('<div style="width:100%;font-family:Segoe UI,Arial;font-size:8px;color:#667;text-align:center">'
            'page <span class="pageNumber"></span> sur <span class="totalPages"></span></div>')
    with sync_playwright() as p:
        navigateur = p.chromium.launch(channel="msedge")
        page = navigateur.new_page()
        for nom in DOCUMENTS:
            rendu = MODELES / f"_rendu_{nom}.html"
            rendu.write_text(env.get_template(f"{nom}.html").render(**contexte), encoding="utf-8")
            try:
                page.goto(rendu.as_uri(), wait_until="networkidle")
                page.pdf(path=str(config.DOCS / f"{nom}.pdf"), prefer_css_page_size=True, print_background=True,
                         display_header_footer=True, header_template="<span></span>", footer_template=pied)
            finally:
                rendu.unlink()
            log(f"{nom}.pdf : {(config.DOCS / f'{nom}.pdf').stat().st_size // 1024} Ko")
        navigateur.close()


if __name__ == "__main__":
    imprimer()
