"""Relance toute la chaîne, de la base vide aux documents.

    python run_all.py                reprend tout, à partir des collectes déjà téléchargées
    python run_all.py --telecharger  télécharge d'abord les publications du jour
    python run_all.py --sans-recette s'arrête avant les tests et les documents

Le parcours dans une vraie fenêtre QGIS (09_captures_qgis.py) n'est pas lancé ici : il se déroule dans un QGIS
ouvert, projet vide, et sa dernière trace reste dans livrables/recette/ihm.json. Aucun projet QGIS connecté à
la base ne doit être ouvert pendant la chaîne : la reconstruction et le test de flux exigent une base sans connexion.
"""
import argparse
import subprocess
import sys
import time

import config
from outils import log


def lancer(*commande, cwd=config.SCRIPTS):
    debut = time.time()
    log("> " + " ".join(str(c) for c in commande[1:]))
    subprocess.run([str(c) for c in commande], cwd=cwd, check=True)
    log(f"  terminé en {time.time() - debut:.0f} s")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--telecharger", action="store_true")
    p.add_argument("--sans-recette", action="store_true")
    args = p.parse_args()

    python = sys.executable
    debut = time.time()
    lancer(python, "00_base.py", "--neuve")
    if args.telecharger:
        lancer(python, "01_telecharger.py")
    lancer(python, "02_charger_sources.py")
    lancer(python, "03_reprise.py")
    lancer(python, "04_controles.py")
    lancer(python, "05_export_eclext.py")
    lancer(python, "06_recette_geo.py")
    lancer(python, "07_jeu_essai.py")
    lancer(config.QGIS_PYTHON, "-u", "08_projets_qgis.py")
    lancer(config.QGIS_PYTHON, "-u", "08b_modele_qgis.py")
    lancer(config.QGIS_PYTHON, "-u", "08c_paquet_qfield.py")
    if not args.sans_recette:
        # Un test en échec n'arrête pas la chaîne : il apparaît dans le cahier de recette
        subprocess.run([python, "-m", "pytest", ".", "-q", "--tb=short", "-p", "no:cacheprovider"], cwd=config.RACINE / "tests")
        lancer(python, "10_cahier_recette.py")
        lancer(python, "11_documents.py")
    log(f"Chaîne terminée en {(time.time() - debut) / 60:.1f} min")
