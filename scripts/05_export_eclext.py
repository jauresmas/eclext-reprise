"""Étape 5 : export au format d'échange EclExt, un dossier par gestionnaire.

    ECLEXT_<ZONE>_V01/
        PointLumineux_<ZONE>_V01.gpkg     classe PointLumineux, en Lambert 93
        PointLumineux_<ZONE>_V01.csv      la même, géométrie en WKT
        fr-<SIREN>-eclairage-exterieur-<emprise>-<date>.xml   métadonnées (section 5.2 du standard)

Les colonnes et les valeurs sont celles des vues du schéma eclext. Un attribut que la source ne donne
pas reste vide : l'export ne comble rien, et la fiche de métadonnées le dit.

    python 05_export_eclext.py
"""
import datetime as dt
import shutil
import warnings
from xml.sax.saxutils import escape

import config
import geopandas as gpd
import pandas as pd
from outils import connexion, curseur, fr, log

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

EMPRISES = {"SDE18": "Cher", "NANTES": "Nantes-Metropole", "LOIRE": "publication-Loire"}

BOOLEENS = ["eclairagePublic", "extinctionNuit", "estAdaptatif"]
REELS = ["puissance", "hauteurFeu", "fluxSource", "fluxLuminaire", "cie3", "ulrNominal", "ulrInstalle",
         "inclinaisonMax", "inclinaisonInstallee"]
ATTRIBUTS = ["identifiant", "statut", "eclairagePublic", "usage", "typeSource", "structure", "support",
             "temperatureCouleur", "puissance", "fabricant", "modele", "photometrie", "hauteurFeu", "fluxSource",
             "fluxLuminaire", "cie3", "ulrNominal", "ulrInstalle", "inclinaisonMax", "inclinaisonInstallee",
             "valideDe", "valideJusque", "datePremiereInstallation", "extinctionNuit", "profilNocturne",
             "estAdaptatif", "eclairageAdaptatif"]


def texte(valeur):
    return f"<gco:CharacterString>{escape(str(valeur))}</gco:CharacterString>"


def metadonnees(nom, siren, emprise, jour, lot, bbox, resume, manquants):
    """Fiche ISO 19139. La conformité au standard est déclarée fausse tant qu'un attribut obligatoire manque."""
    date_iso = f"{jour[:4]}-{jour[4:6]}-{jour[6:]}"
    ouest, sud, est, nord = bbox
    conforme = "true" if manquants == "aucun" else "false"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier>{texte(f"fr-{siren}-eclairage-exterieur-{emprise}-{jour}")}</gmd:fileIdentifier>
  <gmd:language><gmd:LanguageCode codeList="http://www.loc.gov/standards/iso639-2/" codeListValue="fre">fre</gmd:LanguageCode></gmd:language>
  <gmd:characterSet><gmd:MD_CharacterSetCode codeList="MD_CharacterSetCode" codeListValue="utf8"/></gmd:characterSet>
  <gmd:contact><gmd:CI_ResponsibleParty><gmd:organisationName>{texte(config.AUTEUR + ", étude indépendante")}</gmd:organisationName>
    <gmd:role><gmd:CI_RoleCode codeList="CI_RoleCode" codeListValue="author"/></gmd:role></gmd:CI_ResponsibleParty></gmd:contact>
  <gmd:dateStamp><gco:Date>{date_iso}</gco:Date></gmd:dateStamp>
  <gmd:referenceSystemInfo><gmd:MD_ReferenceSystem><gmd:referenceSystemIdentifier><gmd:RS_Identifier>
    <gmd:code>{texte("EPSG:2154")}</gmd:code>
  </gmd:RS_Identifier></gmd:referenceSystemIdentifier></gmd:MD_ReferenceSystem></gmd:referenceSystemInfo>
  <gmd:identificationInfo><gmd:MD_DataIdentification>
    <gmd:citation><gmd:CI_Citation>
      <gmd:title>{texte(f"Éclairage extérieur au format EclExt : {nom}, {emprise}")}</gmd:title>
      <gmd:date><gmd:CI_Date><gmd:date><gco:Date>{date_iso}</gco:Date></gmd:date>
        <gmd:dateType><gmd:CI_DateTypeCode codeList="CI_DateTypeCode" codeListValue="creation"/></gmd:dateType></gmd:CI_Date></gmd:date>
    </gmd:CI_Citation></gmd:citation>
    <gmd:abstract>{texte(resume)}</gmd:abstract>
    <gmd:pointOfContact><gmd:CI_ResponsibleParty><gmd:organisationName>{texte(nom)}</gmd:organisationName>
      <gmd:role><gmd:CI_RoleCode codeList="CI_RoleCode" codeListValue="originator"/></gmd:role></gmd:CI_ResponsibleParty></gmd:pointOfContact>
    <gmd:descriptiveKeywords><gmd:MD_Keywords>
      <gmd:keyword>{texte("éclairage extérieur")}</gmd:keyword>
      <gmd:keyword>{texte("éclairage public")}</gmd:keyword>
      <gmd:keyword>{texte("EclExt")}</gmd:keyword>
    </gmd:MD_Keywords></gmd:descriptiveKeywords>
    <gmd:resourceConstraints><gmd:MD_LegalConstraints><gmd:otherConstraints>{texte(f"Licence de la source : {lot['licence']}")}</gmd:otherConstraints></gmd:MD_LegalConstraints></gmd:resourceConstraints>
    <gmd:language><gmd:LanguageCode codeList="http://www.loc.gov/standards/iso639-2/" codeListValue="fre">fre</gmd:LanguageCode></gmd:language>
    <gmd:topicCategory><gmd:MD_TopicCategoryCode>utilitiesCommunication</gmd:MD_TopicCategoryCode></gmd:topicCategory>
    <gmd:extent><gmd:EX_Extent><gmd:geographicElement><gmd:EX_GeographicBoundingBox>
      <gmd:westBoundLongitude><gco:Decimal>{ouest:.5f}</gco:Decimal></gmd:westBoundLongitude>
      <gmd:eastBoundLongitude><gco:Decimal>{est:.5f}</gco:Decimal></gmd:eastBoundLongitude>
      <gmd:southBoundLatitude><gco:Decimal>{sud:.5f}</gco:Decimal></gmd:southBoundLatitude>
      <gmd:northBoundLatitude><gco:Decimal>{nord:.5f}</gco:Decimal></gmd:northBoundLatitude>
    </gmd:EX_GeographicBoundingBox></gmd:geographicElement></gmd:EX_Extent></gmd:extent>
  </gmd:MD_DataIdentification></gmd:identificationInfo>
  <gmd:distributionInfo><gmd:MD_Distribution><gmd:distributionFormat><gmd:MD_Format>
    <gmd:name>{texte("GeoPackage")}</gmd:name><gmd:version>{texte("1.2")}</gmd:version>
  </gmd:MD_Format></gmd:distributionFormat></gmd:MD_Distribution></gmd:distributionInfo>
  <gmd:dataQualityInfo><gmd:DQ_DataQuality>
    <gmd:report><gmd:DQ_DomainConsistency><gmd:result><gmd:DQ_ConformanceResult>
      <gmd:specification><gmd:CI_Citation><gmd:title>{texte("Géostandard CNIG EclExt v1.1")}</gmd:title>
        <gmd:date><gmd:CI_Date><gmd:date><gco:Date>2022-11-29</gco:Date></gmd:date>
          <gmd:dateType><gmd:CI_DateTypeCode codeList="CI_DateTypeCode" codeListValue="publication"/></gmd:dateType></gmd:CI_Date></gmd:date>
      </gmd:CI_Citation></gmd:specification>
      <gmd:explanation>{texte(f"Attributs obligatoires absents de la source : {manquants}.")}</gmd:explanation>
      <gmd:pass><gco:Boolean>{conforme}</gco:Boolean></gmd:pass>
    </gmd:DQ_ConformanceResult></gmd:result></gmd:DQ_DomainConsistency></gmd:report>
    <gmd:lineage><gmd:LI_Lineage>
      <gmd:statement>{texte(f"Source : {lot['url']}, collecte du {lot['date_collecte']}. Reprise SQL et contrôles décrits dans le dépôt eclext-reprise.")}</gmd:statement>
    </gmd:LI_Lineage></gmd:lineage>
  </gmd:DQ_DataQuality></gmd:dataQualityInfo>
</gmd:MD_Metadata>
"""


def exporter(gestionnaire, nom, siren, source, jour):
    dossier = config.LIVRABLES / "eclext" / f"ECLEXT_{gestionnaire}_V01"
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    conn = connexion()
    try:
        gdf = gpd.read_postgis(
            f"""SELECT {', '.join(f'"{a}"' for a in ATTRIBUTS)}, geometrie FROM eclext.pointlumineux
                WHERE gestionnaire = %(g)s ORDER BY identifiant""",
            conn, geom_col="geometrie", params={"g": gestionnaire})
    finally:
        conn.close()
    gdf = gdf.astype({c: "boolean" for c in BOOLEENS})
    gdf[REELS] = gdf[REELS].apply(pd.to_numeric, errors="coerce").astype("float64")
    gdf["temperatureCouleur"] = gdf["temperatureCouleur"].astype("Int64")

    base = f"PointLumineux_{gestionnaire}_V01"
    gdf.to_file(dossier / f"{base}.gpkg", layer="PointLumineux", driver="GPKG", engine="pyogrio",
                layer_options={"GEOMETRY_NAME": "geometrie"})
    table = pd.DataFrame(gdf.drop(columns="geometrie"))
    for c in BOOLEENS:
        table[c] = table[c].map({True: "true", False: "false"}, na_action="ignore")
    table["geometrie"] = gdf.geometry.to_wkt(rounding_precision=3)
    table.to_csv(dossier / f"{base}.csv", sep=";", index=False, encoding="utf-8")

    with curseur() as cur:
        cur.execute("SELECT url, date_collecte, licence FROM flux.lot WHERE source = %s AND courant", (source,))
        url, date_collecte, licence = cur.fetchone()
        cur.execute("""SELECT string_agg(attribut, ', ' ORDER BY attribut) FROM controle.conformite_attribut
                       WHERE gestionnaire = %s AND obligatoire AND renseignes = 0""", (gestionnaire,))
        manquants = cur.fetchone()[0] or "aucun"
        cur.execute("""SELECT count(*) FROM controle.ecart e JOIN metier.gestionnaire g ON g.id = e.gestionnaire_id
                       WHERE e.regle = 'POS_05' AND g.code = %s""", (gestionnaire,))
        hors_territoire = cur.fetchone()[0]
    resume = (f"Conversion au géostandard CNIG EclExt v1.1 de la donnée ouverte publiée par {nom} "
              f"({fr(len(gdf)).replace(chr(0x202f), ' ')} points lumineux). Étude indépendante, sans lien avec le producteur.")
    if hors_territoire:
        resume += f" {fr(hors_territoire).replace(chr(0x202f), ' ')} points sont situés hors du territoire annoncé par la publication."
    xml = metadonnees(nom, siren, EMPRISES[gestionnaire], jour,
                      {"url": url, "date_collecte": date_collecte, "licence": licence},
                      gdf.to_crs(4326).total_bounds, resume, manquants)
    (dossier / f"fr-{siren}-eclairage-exterieur-{EMPRISES[gestionnaire]}-{jour}.xml").write_text(xml, encoding="utf-8")
    log(f"{gestionnaire} : {fr(len(gdf))} points, attributs obligatoires absents : {manquants}")


if __name__ == "__main__":
    jour = dt.date.today().strftime("%Y%m%d")
    with curseur() as cur:
        cur.execute("SELECT code, nom, siren, source FROM metier.gestionnaire ORDER BY id")
        gestionnaires = cur.fetchall()
    for code, nom, siren, source in gestionnaires:
        exporter(code, nom, siren, source, jour)
