"""Étape 6 : contrôle indépendant des fichiers exportés, avec l'outil recette-geo.

La reprise est contrôlée dans la base (étape 4) ; ici, on relit les fichiers livrés comme le ferait
le destinataire, avec le cahier recette_geo/cahier_eclext.yaml. Un lot « non recevable » n'est pas un
échec du script : c'est la réponse attendue tant que les sources ne donnent pas les attributs obligatoires.

    python 06_recette_geo.py [--zone LOIRE]
"""
import argparse
import os
import subprocess
import sys
import warnings

import config
import geopandas as gpd
from outils import connexion, log

SORTIE = config.LIVRABLES / "recette_geo"
CAHIER = config.RACINE / "recette_geo" / "cahier_eclext.yaml"


def emprises():
    """Territoire annoncé par chaque producteur, d'après le référentiel des communes."""
    warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
    conn = connexion()
    try:
        gdf = gpd.read_postgis(
            """SELECT g.code AS zone, ST_Multi(ST_Union(c.geom))::geometry(MultiPolygon, 2154) AS geom
               FROM metier.gestionnaire g JOIN ref.commune c ON c.departement = g.territoire_annonce
               GROUP BY g.code""", conn, geom_col="geom")
    finally:
        conn.close()
    fichier = SORTIE / "referentiel" / "emprises.gpkg"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.unlink(missing_ok=True)
    gdf.to_file(fichier, layer="emprises", driver="GPKG", engine="pyogrio")


def controler(zone):
    dossier = config.LIVRABLES / "eclext" / f"ECLEXT_{zone}_V01"
    sortie = SORTIE / zone
    env = dict(os.environ, PYTHONPATH=str(config.RECETTE_GEO), PYTHONIOENCODING="utf-8")
    log(f"{zone} : contrôle en cours")
    r = subprocess.run([sys.executable, "-m", "recette_geo", "controler", str(dossier), "-c", str(CAHIER),
                        "-o", str(sortie), "--sans-semantique", "--forcer"],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr[-3000:] or r.stdout[-3000:])
    log(r.stdout.strip()[-600:])
    return r.returncode


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zone", help="un seul gestionnaire (SDE18, NANTES, LOIRE)")
    args = p.parse_args()
    emprises()
    for zone in [args.zone] if args.zone else ["SDE18", "NANTES", "LOIRE"]:
        controler(zone)
