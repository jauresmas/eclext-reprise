"""Étape 4 : contrôles de la reprise, rapprochement des deux bases du Cher, bilans en CSV.

    python 04_controles.py
"""
import csv

import config
from outils import curseur, executer_sql, fr, log


def exporter(cur, requete, chemin):
    cur.execute(requete)
    entetes = [d[0] for d in cur.description]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(entetes)
        w.writerows(cur.fetchall())


if __name__ == "__main__":
    executer_sql("30b_bilan_reprise.sql", "31_controles.sql", "32_rapprochement.sql")
    dossier = config.LIVRABLES / "controle"
    with curseur() as cur:
        exporter(cur, "SELECT * FROM controle.bilan_reprise ORDER BY 1", dossier / "bilan_reprise.csv")
        exporter(cur, "SELECT * FROM controle.bilan_regle WHERE nb_ecarts > 0", dossier / "bilan_regles.csv")
        exporter(cur, """SELECT gestionnaire, attribut, obligatoire, points, taux_conforme, taux_renseigne, origine, champ_source, commentaire
                         FROM controle.conformite_attribut ORDER BY gestionnaire, obligatoire DESC, attribut""",
                 dossier / "conformite_attributs.csv")
        exporter(cur, """SELECT statut, count(*) AS objets, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY distance_m)::numeric, 3) AS distance_mediane_m,
                                max(distance_m) AS distance_max_m
                         FROM controle.rapprochement GROUP BY statut ORDER BY 2 DESC""", dossier / "bilan_rapprochement.csv")
        cur.execute("SELECT * FROM controle.bilan_reprise ORDER BY 1")
        for g, lignes, points, supports, fus, ecartees, ecart in cur.fetchall():
            log(f"{g} : {fr(lignes)} lignes, {fr(points)} points, {fr(supports)} supports, {fus} fusionnées, {ecartees} écartées, écart {ecart}")
        cur.execute("SELECT code, gravite, gestionnaire, nb_ecarts FROM controle.bilan_regle WHERE nb_ecarts > 0")
        for code, gravite, g, n in cur.fetchall():
            log(f"  {code} {gravite:11} {g or '':7} {fr(n)}")
