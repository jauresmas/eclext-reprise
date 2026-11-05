"""Paramètres de la chaîne : sources, chemins, base PostgreSQL."""
import os
import sys
from pathlib import Path

# L'installateur de PostgreSQL déclare PROJ_LIB vers la base PROJ de PostGIS, plus ancienne que
# celle de pyproj : la chaîne Python l'ignore, le serveur PostgreSQL la retrouve au démarrage.
PROJ_LIB_POSTGIS = None
for _var in ("PROJ_LIB", "PROJ_DATA"):
    if "PostgreSQL" in os.environ.get(_var, ""):
        PROJ_LIB_POSTGIS = os.environ.pop(_var)

for _flux in (sys.stdout, sys.stderr):
    if hasattr(_flux, "reconfigure"):
        _flux.reconfigure(encoding="utf-8", errors="replace")

RACINE = Path(__file__).resolve().parents[1]
SOURCES = RACINE / "data" / "sources"
CORRESPONDANCES = RACINE / "data" / "correspondances"
SQL = RACINE / "sql"
LIVRABLES = RACINE / "livrables"
SCRIPTS = RACINE / "scripts"
DOCS = RACINE / "docs"

# --- Base PostgreSQL / PostGIS --------------------------------------------------------------
# Instance propre au projet (port dédié, connexion locale sans mot de passe), dans data/pgdata
PG_BIN = Path(r"C:\Program Files\PostgreSQL\15\bin")
PG_DATA = RACINE / "data" / "pgdata"
PG_HOST = "localhost"
PG_PORT = 5436
PG_DB = os.environ.get("ECLEXT_BASE", "eclext")  # la recette rejoue les flux sur une copie
PG_SUPERUSER = "postgres"

QGIS_PYTHON = Path(r"C:\Program Files\QGIS 3.34.12\bin\python-qgis-ltr.bat")
QGIS_BIN = Path(r"C:\Program Files\QGIS 3.34.12\bin\qgis-ltr-bin.exe")

# Outil de contrôle des livraisons (github.com/jauresmas/recette-geo) : dossier du dépôt
RECETTE_GEO = Path(os.environ.get("RECETTE_GEO", RACINE.parent / "recette-geo"))

AUTEUR = "Jaurès DAA-HINGBANON"
CLIENT_HTTP = "eclext-reprise/1.0"

# --- Sources ouvertes -----------------------------------------------------------------------
# `jeu` est l'identifiant data.gouv.fr : l'adresse du fichier est relue à chaque collecte,
# car certains producteurs datent leurs fichiers.
SOURCES_OUVERTES = {
    "sde18": {
        "titre": "Supports d'éclairage public du SDE18",
        "producteur": "Syndicat départemental d'énergie du Cher",
        "jeu": "673b1255be2baa1d2a71c950",
        "format": "json",
        "fichier": "supports-ep.json",
    },
    "ccf": {
        "titre": "Inventaire intercommunal de l'éclairage public",
        "producteur": "Communauté de communes Cœur de France",
        "jeu": "6920fea1ae83a56f12a19776",
        "format": "csv",
        "fichier": "candelabres-communautaire.csv",
    },
    "nantes": {
        "titre": "Luminaires d'éclairage public de Nantes Métropole",
        "producteur": "Nantes Métropole",
        "jeu": "626888d1110b508648f11a3b",
        "format": "csv",
        "fichier": "luminaires-nantes-metropole.csv",
    },
    "loire": {
        "titre": "Éclairage public sur le département de la Loire",
        "producteur": "Loire Forez Agglomération",
        "jeu": "65a53c04c6b2ecabaf745104",
        "format": "csv",
        "fichier": "eclairage-public-loire-42.csv",
    },
}

# Contours communaux : API Découpage administratif (geo.api.gouv.fr)
COMMUNES = {
    "dep18": "https://geo.api.gouv.fr/departements/18/communes?fields=nom,code,codeDepartement,codeEpci&format=geojson&geometry=contour",
    "dep42": "https://geo.api.gouv.fr/departements/42/communes?fields=nom,code,codeDepartement,codeEpci&format=geojson&geometry=contour",
    # La publication intitulée Loire se trouve en réalité en Haute-Savoie (règle POS_05)
    "dep74": "https://geo.api.gouv.fr/departements/74/communes?fields=nom,code,codeDepartement,codeEpci&format=geojson&geometry=contour",
    "epci_nantes": "https://geo.api.gouv.fr/epcis/244400404/communes?fields=nom,code,codeDepartement,codeEpci&format=geojson&geometry=contour",
}
