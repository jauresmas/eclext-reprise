"""Étape 8c : paquet QField de la collectivité, pour déclarer une panne depuis le terrain, même sans réseau.

Le paquet est extrait avec le compte de la collectivité : il ne contient que ce que ce compte a le droit de voir.
Il ne garde aucune connexion à la base et aucun mot de passe. Les pannes saisies restent dans
signalements_terrain.gpkg jusqu'au retour du téléphone : 13_importer_terrain.py les verse alors dans la base.

    python-qgis-ltr.bat 08c_paquet_qfield.py
    python-qgis-ltr.bat 08c_paquet_qfield.py --compte mairie_reze
"""
import argparse
import importlib
import tempfile
import zipfile
from pathlib import Path

import config
from outils import curseur
from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsDataSourceUri, QgsDatumTransform,
                       QgsDefaultValue, QgsEditorWidgetSetup, QgsFillSymbol, QgsMapLayer, QgsProject, QgsRectangle, QgsReferencedRectangle,
                       QgsSnappingConfig, QgsTolerance, QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes)

qp = importlib.import_module("08_projets_qgis")  # mêmes styles et mêmes réglages de fiche que les projets de bureau

SORTIE = config.RACINE / "projets" / "qfield"
PORTEE_M = 100

POINTS = """SELECT p.id, p.code, c.nom AS commune, s.voie, p.type_source, coalesce(t.description, p.type_source) AS source, p.puissance_w,
                   p.temperature_couleur, p.geom
            FROM metier.point_lumineux p
            LEFT JOIN metier.support s ON s.id = p.support_id
            LEFT JOIN ref.type_source t ON t.code = p.type_source
            LEFT JOIN ref.commune c ON c.insee = p.insee
            WHERE p.retire_le IS NULL"""
EN_COURS = """SELECT s.id, s.point_id, n.description AS nature, st.description AS statut, to_char(s.declare_le, 'DD/MM/YYYY') AS declare_le,
                     s.description, s.jeu_essai, s.geom
              FROM exploitation.signalement s
              JOIN ref.nature_signalement n ON n.code = s.nature
              JOIN ref.statut_signalement st ON st.code = s.statut
              WHERE s.statut IN ('OUVERT', 'PRIS_EN_COMPTE')"""
COMMUNES = "SELECT insee, nom, geom FROM ref.commune WHERE insee = ANY (admin.mes_communes())"

# La fiche s'ouvre sur le point le plus proche de l'endroit désigné : l'agent vérifie le code et la rue, il ne les saisit pas
PROCHE = "array_first(overlay_nearest('Points lumineux', {}, max_distance:=" + str(PORTEE_M) + "))"
AUTO = {"point_id": PROCHE.format('"id"'), "code_point": PROCHE.format('"code"'), "voie": PROCHE.format('"voie"'),
        "distance_m": f"round(distance($geometry, {PROCHE.format('$geometry')}))"}


def extraire(compte, requete, cle, wkb, gpkg, table):
    """Le périmètre vient de la base : la requête passe par le compte de la collectivité."""
    uri = QgsDataSourceUri()
    uri.setConnection(config.PG_HOST, str(config.PG_PORT), config.PG_DB, compte, "")
    uri.setDataSource("", f"({requete})", "geom", "", cle)
    uri.setSrid("2154")
    uri.setWkbType(wkb)
    source = QgsVectorLayer(uri.uri(False), table, "postgres")
    assert source.isValid(), f"{table} ({compte}) : {source.error().message()}"
    ecrire(source, gpkg, table)
    return source.featureCount()


def ecrire(source, gpkg, table):
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = table
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if gpkg.exists() else QgsVectorFileWriter.CreateOrOverwriteFile
    erreur, message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(source, str(gpkg), QgsCoordinateTransformContext(), options)
    assert erreur == QgsVectorFileWriter.NoError, f"{table} : {message}"


def couche(gpkg, table, nom):
    lyr = QgsVectorLayer(f"{gpkg}|layername={table}", nom, "ogr")
    assert lyr.isValid(), f"{nom} : {lyr.error().message()}"
    QgsProject.instance().addMapLayer(lyr, False)
    return lyr


def fiche_panne(saisie, natures):
    for champ, libelle in {"code_point": "Point lumineux le plus proche", "voie": "Rue", "distance_m": "Distance au repère (m)",
                           "nature": "Nature", "description": "Description", "photo": "Photo"}.items():
        saisie.setFieldAlias(qp.idx(saisie, champ), libelle)
    for champ, expression in AUTO.items():
        saisie.setDefaultValueDefinition(qp.idx(saisie, champ), QgsDefaultValue(expression, True))
    qp.defaut(saisie, "uuid_terrain", "uuid('WithoutBraces')")
    qp.defaut(saisie, "constate_ms", "epoch(now())")
    qp.defaut(saisie, "nature", "'PANNE'")
    saisie.setEditorWidgetSetup(qp.idx(saisie, "nature"), QgsEditorWidgetSetup("ValueMap", {"map": [{libelle: code} for code, libelle in natures]}))
    qp.texte_long(saisie, "description")
    # QField affiche ici l'appareil photo et la galerie ; le chemin reste relatif au projet (DCIM/...)
    saisie.setEditorWidgetSetup(qp.idx(saisie, "photo"), QgsEditorWidgetSetup("ExternalResource", {
        "DocumentViewer": 1, "DocumentViewerHeight": 0, "DocumentViewerWidth": 0, "FileWidget": True, "FileWidgetButton": True,
        "RelativeStorage": 1, "UseLink": False, "FullUrl": False}))
    qp.masque(saisie, "fid", "uuid_terrain", "point_id", "constate_ms")
    qp.lecture_seule(saisie, "code_point", "voie", "distance_m")
    # La contrainte porte sur un champ visible : un champ masqué griserait OK sans donner de motif
    qp.contrainte(saisie, "code_point", '"code_point" IS NOT NULL', f"Aucun point lumineux à moins de {PORTEE_M} m : déplacez le repère vers un point")
    qp.contrainte(saisie, "description", "\"nature\" <> 'AUTRE' OR length(trim(\"description\")) > 0", "Décrivez ce que vous avez constaté")
    qp.onglets(saisie, [("Panne", ["code_point", "voie", "distance_m", "nature", "description", "photo"])])
    saisie.setDisplayExpression("\"nature\" || coalesce(', ' || \"code_point\", '')")


def construire(dossier, natures):
    projet = QgsProject.instance()
    projet.clear()
    projet.setTitle("Éclairage : déclarer une panne")
    # Le fond de plan est en pseudo-Mercator : sans reprojection, il reste net et rapide sur un téléphone
    projet.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    projet.setFileName(str(dossier / "eclairage_terrain.qgs"))

    reference = dossier / "reference.gpkg"
    point = couche(reference, "points_lumineux", "Points lumineux")
    en_cours = couche(reference, "signalements_en_cours", "Signalements en cours")
    commune = couche(reference, "communes", "Communes")
    saisie = couche(dossier / "signalements_terrain.gpkg", "signalements_terrain", "Signaler une panne")
    fond = qp.fond_ign()
    projet.addMapLayer(fond, False)
    lambert, mercator = QgsCoordinateReferenceSystem("EPSG:2154"), QgsCoordinateReferenceSystem("EPSG:3857")
    contexte = projet.transformContext()
    contexte.addCoordinateOperation(lambert, mercator, QgsDatumTransform.operations(lambert, mercator)[0].proj, True)
    projet.setTransformContext(contexte)

    fiche_panne(saisie, natures)
    for champ, libelle in {"code": "Point lumineux", "commune": "Commune", "voie": "Rue", "source": "Type de source",
                           "puissance_w": "Puissance (W)", "temperature_couleur": "Température de couleur (K)"}.items():
        point.setFieldAlias(qp.idx(point, champ), libelle)
    qp.masque(point, "fid", "id", "type_source")
    point.setDisplayExpression("\"code\" || coalesce(', ' || \"voie\", '')")
    for champ, libelle in {"nature": "Nature", "statut": "Statut", "declare_le": "Déclaré le", "description": "Description", "jeu_essai": "Jeu d'essai"}.items():
        en_cours.setFieldAlias(qp.idx(en_cours, champ), libelle)
    qp.booleens(en_cours, "jeu_essai")
    qp.masque(en_cours, "fid", "id", "point_id")
    en_cours.setDisplayExpression("\"nature\" || ' du ' || \"declare_le\"")

    qp.regles(point, qp.REGLES_SOURCE, taille=2.6)
    qp.echelle_max(point, 100000)
    qp.etiquettes(point, '"code"', 1500, taille=8)
    qp.regles(en_cours, [("Signalement en cours", "TRUE", "#f28e2b")], taille=5.0, forme="triangle", contour="#222222")
    qp.regles(saisie, [("Panne déclarée ici", "TRUE", "#d7301f")], taille=6.0, forme="triangle", contour="#222222")
    commune.renderer().setSymbol(QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#6b6b6b", "outline_width": "0.4", "outline_style": "dash"}))

    for lyr in [point, en_cours, commune]:
        lyr.setReadOnly(True)
    for lyr in [commune, fond]:
        lyr.setFlags(lyr.flags() & ~QgsMapLayer.Identifiable)
    arbre = projet.layerTreeRoot()
    for lyr in [saisie, en_cours, point, commune, fond]:
        arbre.addLayer(lyr)

    # Le repère s'accroche au point lumineux voisin
    accroche = QgsSnappingConfig(projet)
    accroche.setEnabled(True)
    accroche.setMode(QgsSnappingConfig.AdvancedConfiguration)
    accroche.setIndividualLayerSettings(point, QgsSnappingConfig.IndividualLayerSettings(True, Qgis.SnappingType.Vertex, 25, QgsTolerance.Pixels, 0, 0))
    projet.setSnappingConfig(accroche)

    emprise = QgsRectangle()
    for entite in commune.getFeatures():
        emprise.combineExtentWith(entite.geometry().boundingBox())
    projet.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(emprise, lambert))

    assert projet.write(), "écriture du projet QField impossible"
    projet.clear()


def paquet(compte):
    with curseur(compte) as cur:
        cur.execute("SELECT code, description FROM ref.nature_signalement ORDER BY description")
        natures = cur.fetchall()
    with tempfile.TemporaryDirectory() as temporaire:
        dossier = Path(temporaire)
        reference = dossier / "reference.gpkg"
        points = extraire(compte, POINTS, "id", QgsWkbTypes.Point, reference, "points_lumineux")
        en_cours = extraire(compte, EN_COURS, "id", QgsWkbTypes.Point, reference, "signalements_en_cours")
        communes = extraire(compte, COMMUNES, "insee", QgsWkbTypes.MultiPolygon, reference, "communes")
        modele = QgsVectorLayer("Point?crs=EPSG:2154&field=uuid_terrain:string(40)&field=point_id:int8&field=code_point:string(40)&field=voie:string(200)"
                                "&field=distance_m:double&field=nature:string(20)&field=description:string&field=photo:string&field=constate_ms:int8",
                                "signalements_terrain", "memory")
        ecrire(modele, dossier / "signalements_terrain.gpkg", "signalements_terrain")
        construire(dossier, natures)

        SORTIE.mkdir(parents=True, exist_ok=True)
        archive = SORTIE / f"eclairage_terrain_{compte}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("DCIM/", "")
            for nom in ["eclairage_terrain.qgs", "reference.gpkg", "signalements_terrain.gpkg"]:
                z.write(dossier / nom, nom)
    print(f"{archive} : {points} points, {en_cours} signalements en cours, {communes} commune(s), {archive.stat().st_size // 1024} Ko", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--compte", default="demo_commune", help="compte de la collectivité : son périmètre fait le contenu du paquet")
    args = p.parse_args()
    app = QgsApplication([], True)
    app.initQgis()
    paquet(args.compte)
    QgsProject.instance().clear()
    app.exitQgis()
