"""Étape 3 : reprise des sources brutes vers la base métier.

Les tables de correspondance (data/correspondances) sont rechargées, puis chaque source est
reprise. Le script est relançable : ce qui n'a pas changé n'est pas réécrit.

    python 03_reprise.py
"""
import csv

import config
from outils import curseur, executer_sql, log


def charger_csv(cur, nom, table, colonnes):
    with open(config.CORRESPONDANCES / nom, encoding="utf-8", newline="") as f:
        # Une case vide devient NULL, sauf valeur_source : la correspondance d'une valeur vide est une vraie ligne
        lignes = [[(ligne[c] if ligne[c] != "" or c == "valeur_source" else None) for c in colonnes]
                  for ligne in csv.DictReader(f, delimiter=";")]
    cur.execute(f"TRUNCATE {table}")
    marques = ", ".join(["%s"] * len(colonnes))
    cur.executemany(f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({marques})", lignes)
    return len(lignes)


if __name__ == "__main__":
    with curseur() as cur:
        n = charger_csv(cur, "correspondances.csv", "ref.correspondance",
                        ["source", "champ_source", "valeur_source", "attribut_cible", "valeur_cible", "certitude", "commentaire"])
        m = charger_csv(cur, "origine_attributs.csv", "ref.origine_attribut",
                        ["gestionnaire", "attribut", "origine", "champ_source", "commentaire"])
    log(f"Correspondances : {n} valeurs, {m} origines d'attributs")
    executer_sql("10_reprise_sde18.sql", "11_reprise_nantes.sql", "12_reprise_loire.sql", "13_enrichir_ccf.sql")
    with curseur() as cur:
        cur.execute("""SELECT g.code, (SELECT count(*) FROM metier.armoire a WHERE a.gestionnaire_id = g.id),
                              (SELECT count(*) FROM metier.support s WHERE s.gestionnaire_id = g.id),
                              (SELECT count(*) FROM metier.point_lumineux p WHERE p.gestionnaire_id = g.id)
                       FROM metier.gestionnaire g ORDER BY g.id""")
        for code, armoires, supports, points in cur.fetchall():
            log(f"  {code} : {armoires} armoires, {supports} supports, {points} points lumineux")
