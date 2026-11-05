"""Étape 7 : jeu d'essai de la recette, pour tester les fiches et les droits.

Les sources ne publient aucun historique de maintenance : les signalements et les interventions sont créés
ici, sur de vrais points du patrimoine, et portent tous jeu_essai = true. Le script remplace le jeu d'essai
précédent et ne touche à rien d'autre. Comptes créés : demo_commune, demo_entreprise, demo_entreprise_b.

    python 07_jeu_essai.py
"""
from outils import curseur, executer_sql, log

if __name__ == "__main__":
    executer_sql("42_jeu_essai.sql")
    with curseur() as cur:
        cur.execute("""SELECT (SELECT count(*) FROM exploitation.signalement WHERE jeu_essai),
                              (SELECT count(*) FROM exploitation.intervention WHERE jeu_essai)""")
        signalements, interventions = cur.fetchone()
    log(f"Jeu d'essai : {signalements} signalements, {interventions} interventions")
