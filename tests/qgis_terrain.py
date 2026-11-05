"""Joue le rôle du téléphone : ouvre le paquet QField hors de son dossier d'origine et y saisit des pannes.

QField s'appuie sur le moteur de QGIS : les valeurs par défaut et les contraintes sont évaluées ici par le même code.
Ce script ne remplace pas l'essai sur un vrai téléphone (vérification T-MAN-06 du cahier de recette).

    python-qgis-ltr.bat tests/qgis_terrain.py paquet.zip dossier_de_travail sortie.json
"""
import json
import os
import sys
import time
import traceback
import zipfile
from pathlib import Path

from qgis.core import (Qgis, QgsApplication, QgsFieldConstraints, QgsGeometry, QgsPointXY, QgsProject, QgsVectorDataProvider, QgsVectorLayerUtils)
from qgis.PyQt.QtGui import QColor, QImage


def erreurs(couche, entite):
    return [champ.name() for i, champ in enumerate(couche.fields())
            if not QgsVectorLayerUtils.validateAttribute(couche, entite, i, QgsFieldConstraints.ConstraintStrengthHard)[0]]


def creer(couche, x, y):
    return QgsVectorLayerUtils.createFeature(couche, QgsGeometry.fromPointXY(QgsPointXY(x, y)), {}, couche.createExpressionContext())


def verifier(archive, travail, sortie):
    r = {}
    travail.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        r["fichiers"] = sorted(z.namelist())
        z.extractall(travail)
    texte = (travail / "eclairage_terrain.qgs").read_text(encoding="utf-8")
    r["traces_de_base"] = [mot for mot in ("host=", "password", "dbname=", 'provider="postgres"', "demo_commune", "AppData", Path(__file__).resolve().parents[1].as_posix()) if mot in texte]

    projet = QgsProject.instance()
    r["lecture"] = projet.read(str(travail / "eclairage_terrain.qgs"))
    couches = {c.name(): c for c in projet.mapLayers().values()}
    r["couches"] = sorted(couches)
    r["invalides"] = [nom for nom, c in couches.items() if not c.isValid() and nom != "Plan IGN"]
    r["sources_hors_paquet"] = [nom for nom, c in couches.items() if c.providerType() == "ogr" and not Path(c.source().split("|")[0]).resolve().is_relative_to(travail.resolve())]
    r["fournisseurs"] = {nom: c.providerType() for nom, c in couches.items()}
    saisie, point = couches["Signaler une panne"], couches["Points lumineux"]

    r["modifiables"] = sorted(nom for nom, c in couches.items() if c.type() == 0 and not c.readOnly())
    r["points"] = point.featureCount()
    r["communes"] = sorted(couches["Communes"].uniqueValues(couches["Communes"].fields().indexOf("insee")))
    r["signalements_en_cours"] = couches["Signalements en cours"].featureCount()
    r["saisies_au_depart"] = saisie.featureCount()
    r["onglets"] = [o.name() for o in saisie.editFormConfig().tabs()]
    r["champs_fiche"] = [e.name() for e in saisie.editFormConfig().tabs()[0].children()]
    r["widget_photo"] = saisie.editorWidgetSetup(saisie.fields().indexOf("photo")).type()
    r["stockage_photo"] = saisie.editorWidgetSetup(saisie.fields().indexOf("photo")).config().get("RelativeStorage")
    accroche = projet.snappingConfig()
    r["accroche"] = accroche.enabled() and accroche.individualLayerSettings(point).enabled() and bool(accroche.individualLayerSettings(point).typeFlag() & Qgis.SnappingType.Vertex)

    # Le repère posé à 3 m d'un point : la fiche s'ouvre sur ce point
    cible = sorted(point.getFeatures(), key=lambda f: f["code"])[100]
    position = cible.geometry().asPoint()
    debut = time.time()
    a = creer(saisie, position.x() + 3, position.y())
    r["duree_fiche_s"] = round(time.time() - debut, 3)
    r["attendu"] = {"id": cible["id"], "code": cible["code"], "voie": cible["voie"]}
    r["propose"] = {c: a[c] for c in ("point_id", "code_point", "voie", "distance_m", "nature")}
    r["uuid"] = a["uuid_terrain"]
    r["constate_ms"] = a["constate_ms"]
    r["erreurs_fiche_correcte"] = erreurs(saisie, a)

    # Le repère posé loin de tout point : la fiche ne peut pas être validée
    etendue = point.extent()
    loin = creer(saisie, etendue.xMaximum() + 5000, etendue.yMaximum() + 5000)
    r["loin_code"] = None if loin["code_point"] in (None, "") or str(loin["code_point"]) == "NULL" else loin["code_point"]
    r["loin_erreurs"] = erreurs(saisie, loin)

    # « Autre » sans description : refusé ; avec description : accepté
    autre = creer(saisie, position.x(), position.y())
    autre["nature"] = "AUTRE"
    autre["description"] = None
    r["autre_sans_description"] = erreurs(saisie, autre)
    autre["description"] = "Branche sur le luminaire"
    r["autre_avec_description"] = erreurs(saisie, autre)

    # Deux pannes enregistrées, dont une avec photo, comme QField les écrit
    (travail / "DCIM").mkdir(exist_ok=True)
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(QColor("#336699"))
    r["photo_ecrite"] = image.save(str(travail / "DCIM" / "20261105120000000.jpg"), "JPG")
    a["description"] = "Éteint depuis l'orage d'hier"
    a["photo"] = "DCIM/20261105120000000.jpg"
    autre["photo"] = None
    saisie.startEditing()
    r["ajout"] = saisie.addFeatures([a, autre])
    r["enregistre"] = saisie.commitChanges()
    r["saisies_a_la_fin"] = saisie.featureCount()
    projet.clear()
    Path(sortie).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        verifier(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
    except Exception:
        traceback.print_exc()  # os._exit, qui évite un plantage de QGIS à la fermeture, l'avalerait
    finally:
        sys.stdout.flush()
        os._exit(0)
