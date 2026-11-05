"""T-ECL : les fichiers livrés respectent le format d'échange ; relus sans passer par la base."""
import json
import re
import warnings
import xml.etree.ElementTree as ET

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
import yaml
from conftest import RACINE, lignes, valeur

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

ZONES = ["SDE18", "NANTES", "LOIRE"]
SIREN = {"SDE18": "241800549", "NANTES": "244400404", "LOIRE": "200065886"}
OBLIGATOIRES = ["statut", "eclairagePublic", "usage", "typeSource", "structure", "support", "temperatureCouleur", "puissance",
                "valideDe", "extinctionNuit", "estAdaptatif"]
NS = {"gmd": "http://www.isotc211.org/2005/gmd", "gco": "http://www.isotc211.org/2005/gco"}


def dossier(zone):
    return RACINE / "livrables" / "eclext" / f"ECLEXT_{zone}_V01"


@pytest.fixture(scope="module")
def fichiers():
    return {z: gpd.read_file(dossier(z) / f"PointLumineux_{z}_V01.gpkg", layer="PointLumineux", engine="pyogrio") for z in ZONES}


@pytest.mark.parametrize("zone", ZONES)
def test_nommage(constat, zone):
    """T-ECL-01 : le dossier contient les données et une fiche de métadonnées nommée selon la section 5.2"""
    noms = sorted(p.name for p in dossier(zone).iterdir())
    fiche = [n for n in noms if n.endswith(".xml")]
    constat(fiche[0])
    assert len(noms) == 3 and re.fullmatch(rf"fr-{SIREN[zone]}-eclairage-exterieur-[A-Za-z-]+-\d{{8}}\.xml", fiche[0])


@pytest.mark.parametrize("zone", ZONES)
def test_comptage(fichiers, su, constat, zone):
    """T-ECL-02 : le fichier a autant de points que la base, sans point retiré"""
    attendu = valeur(su, "SELECT count(*) FROM eclext.pointlumineux WHERE gestionnaire = %s", zone)
    constat(f"{len(fichiers[zone])} points dans le fichier, {attendu} dans la base")
    assert len(fichiers[zone]) == attendu


@pytest.mark.parametrize("zone", ZONES)
def test_structure(fichiers, constat, zone):
    """T-ECL-03 : géométrie ponctuelle en Lambert 93, nom de couche et de colonnes du standard"""
    infos = pyogrio.read_info(dossier(zone) / f"PointLumineux_{zone}_V01.gpkg", layer="PointLumineux")
    gdf = fichiers[zone]
    constat(f"{infos['geometry_type']}, {gdf.crs.to_epsg()}, {len(infos['fields'])} attributs")
    assert infos["geometry_type"] == "Point" and gdf.crs.to_epsg() == 2154
    assert set(OBLIGATOIRES) <= set(infos["fields"]) and "id" not in infos["fields"] and "gestionnaire" not in infos["fields"]


@pytest.mark.parametrize("zone", ZONES)
def test_identifiants(fichiers, constat, zone):
    """T-ECL-04 : identifiants uniques, avec les seuls caractères permis par la section 4.4"""
    identifiants = fichiers[zone]["identifiant"]
    fautifs = int((~identifiants.str.fullmatch(r"[A-Za-z0-9._-]+")).sum())
    constat(f"{identifiants.nunique()} identifiants distincts, {fautifs} mal formés")
    assert identifiants.is_unique and fautifs == 0


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("colonne", ["valideDe", "valideJusque", "datePremiereInstallation"])
def test_dates(fichiers, constat, zone, colonne):
    """T-ECL-05 : les dates sont écrites sur 8 chiffres, AAAAMMJJ, et sont de vraies dates"""
    dates = fichiers[zone][colonne].dropna()
    fautives = int((pd.to_datetime(dates, format="%Y%m%d", errors="coerce").isna()).sum()) if len(dates) else 0
    constat(f"{len(dates)} dates, {fautives} fautives")
    assert fautives == 0


@pytest.mark.parametrize("zone", ZONES)
def test_listes(fichiers, su, constat, zone):
    """T-ECL-06 : toutes les valeurs énumérées appartiennent aux listes du standard"""
    gdf = fichiers[zone]
    listes = {"usage": "usage", "typeSource": "type_source", "structure": "structure_luminaire", "support": "support_luminaire",
              "statut": "statut_installation"}
    hors_liste = {}
    for colonne, table in listes.items():
        permis = {r[0] for r in lignes(su, f"SELECT code FROM ref.{table}")}
        n = int((~gdf[colonne].dropna().isin(permis)).sum())
        if n:
            hors_liste[colonne] = n
    constat(f"{len(listes)} listes vérifiées, {len(hors_liste)} écart")
    assert not hors_liste


@pytest.mark.parametrize("zone", ZONES)
def test_rien_n_est_invente(fichiers, su, constat, zone):
    """T-ECL-07 : un attribut que la source ne donne pas reste vide ou inconnu : l'export ne comble rien"""
    absents = [r[0] for r in lignes(su, "SELECT attribut FROM controle.conformite_attribut WHERE gestionnaire = %s AND obligatoire AND renseignes = 0", zone)]
    gdf = fichiers[zone]
    remplis = [a for a in absents if gdf[a].dropna().astype(str).isin(["XX", "AU"]).sum() != gdf[a].notna().sum()]
    constat(f"attributs absents de la source : {', '.join(absents)}")
    assert absents and not remplis


@pytest.mark.parametrize("zone", ZONES)
def test_csv_identique(fichiers, constat, zone):
    """T-ECL-08 : le CSV donne les mêmes objets que le GeoPackage, avec des booléens en true et false"""
    table = pd.read_csv(dossier(zone) / f"PointLumineux_{zone}_V01.csv", sep=";", dtype=str)
    booleens = set(table["eclairagePublic"].dropna().unique())
    constat(f"{len(table)} lignes, valeurs de eclairagePublic : {sorted(booleens)}")
    assert set(table["identifiant"]) == set(fichiers[zone]["identifiant"]) and booleens <= {"true", "false"}
    assert table["geometrie"].str.startswith("POINT").all()


@pytest.mark.parametrize("zone", ZONES)
def test_metadonnees(su, constat, zone):
    """T-ECL-09 : la fiche de métadonnées déclare le standard, et se dit non conforme tant qu'il manque un attribut"""
    fiche = next(dossier(zone).glob("*.xml"))
    racine = ET.parse(fiche).getroot()
    conforme = racine.find(".//gmd:DQ_ConformanceResult/gmd:pass/gco:Boolean", NS).text
    explication = racine.find(".//gmd:DQ_ConformanceResult/gmd:explanation/gco:CharacterString", NS).text
    constat(f"pass = {conforme} ; {explication}")
    assert conforme == "false" and "absents" in explication
    assert "EclExt" in racine.find(".//gmd:specification//gmd:title/gco:CharacterString", NS).text


def test_cahier_coherent_avec_la_base(su, constat):
    """T-ECL-10 : les listes du cahier recette-geo sont celles de la base, valeur pour valeur"""
    cahier = yaml.safe_load((RACINE / "recette_geo" / "cahier_eclext.yaml").read_text(encoding="utf-8"))
    champs = cahier["couches"]["pointlumineux"]["champs"]
    listes = {"usage": "usage", "typeSource": "type_source", "structure": "structure_luminaire", "support": "support_luminaire",
              "statut": "statut_installation", "eclairageAdaptatif": "eclairage_adaptatif"}
    for champ, table in listes.items():
        assert set(champs[champ]["domaine"]) == {r[0] for r in lignes(su, f"SELECT code FROM ref.{table}")}, champ
    assert all(champs[a].get("obligatoire") for a in OBLIGATOIRES)
    constat(f"{len(listes)} listes identiques, {len(OBLIGATOIRES)} attributs obligatoires")


@pytest.mark.parametrize("zone, bloquantes", [("SDE18", 1), ("NANTES", 0), ("LOIRE", 18104)])
def test_recette_geo(constat, zone, bloquantes):
    """T-ECL-11 : le contrôle indépendant par recette-geo refuse les lots et retrouve l'anomalie de territoire"""
    fichier = RACINE / "livrables" / "recette_geo" / zone / f"recette_{zone}_V01_resultats.json"
    r = json.loads(fichier.read_text(encoding="utf-8"))
    decision = r["recevabilite"]
    constat(f"{decision['statut']} : {' ; '.join(decision['motifs'])}")
    assert decision["statut"] == "NON RECEVABLE" and decision["bloquante"] == bloquantes
