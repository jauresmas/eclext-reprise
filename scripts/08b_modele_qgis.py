"""Étape 8 bis : la reprise de Nantes refaite avec le modeleur graphique de QGIS, puis comparée à la voie SQL.

La reprise de référence est écrite en SQL. Le modèle modeles/reprise_nantes_eclext.model3 refait son cœur par une
autre voie, sans passer par la base : position, type de source, type de support, puissance, température de couleur.
Il s'ouvre dans la boîte à outils de QGIS et se relance sur un nouveau fichier. Le script le construit, l'exécute
et écrit la comparaison, objet par objet, dans livrables/recette/croisement_modele.json.

    python-qgis-ltr.bat -u 08b_modele_qgis.py
"""
import json
import math
import os
import sys
import traceback

import config
import psycopg2
from qgis.core import (QgsApplication, QgsProcessingContext, QgsProcessingFeedback, QgsProcessingModelAlgorithm,
                       QgsProcessingModelChildAlgorithm, QgsProcessingModelChildParameterSource as Source,
                       QgsProcessingModelOutput, QgsProcessingModelParameter, QgsProcessingParameterVectorLayer,
                       QgsProject, QgsVectorLayer)
from qgis.PyQt.QtCore import QPointF, QVariant

MODELE = config.RACINE / "modeles" / "reprise_nantes_eclext.model3"
RESULTAT = config.LIVRABLES / "recette" / "croisement_modele.json"
SORTIE_MODELE = "Points lumineux au format EclExt"

FOYER = '"Identifiant du  foyer"'
PUISSANCE = '"Puissance du foyer (W)"'
DESIGNATION = '"Désignation de la lampe"'
ATTRIBUTS = [
    ("identifiant", FOYER, QVariant.String),
    ("statut", "'functional'", QVariant.String),
    ("typeSource", "coalesce(\"lampe_valeur_cible\", 'XX')", QVariant.String),
    ("support", "coalesce(\"support_valeur_cible\", 'XX')", QVariant.String),
    ("puissance", f"if(try(to_real({PUISSANCE})) > 0, to_real({PUISSANCE}), NULL)", QVariant.Double),
    ("temperatureCouleur", f"try(to_int(nullif(regexp_substr(string_to_array({DESIGNATION}, ' ')[4], '^([0-9]{{4}})$'), '')))", QVariant.Int),
]


def construire():
    modele = QgsProcessingModelAlgorithm("Reprise de Nantes Métropole vers EclExt", "Éclairage extérieur")
    modele.setHelpContent({"ALG_DESC": "Refait par le modeleur la reprise SQL de sql/11_reprise_nantes.sql, pour le cœur des attributs."})
    for nom, description, x in [("source", "Fichier des luminaires", 100), ("correspondances", "Table des correspondances", 480)]:
        modele.addModelParameter(QgsProcessingParameterVectorLayer(nom, description), QgsProcessingModelParameter(nom))
        parametre = modele.parameterComponent(nom)
        parametre.setPosition(QPointF(x, 60))
        modele.addModelParameter(modele.parameterDefinition(nom).clone(), parametre)

    def etape(ident, algorithme, description, x, y, **parametres):
        enfant = QgsProcessingModelChildAlgorithm(algorithme)
        enfant.setChildId(ident)
        enfant.setDescription(description)
        enfant.setPosition(QPointF(x, y))
        for nom, valeur in parametres.items():
            enfant.addParameterSources(nom, [valeur if isinstance(valeur, Source) else Source.fromStaticValue(valeur)])
        return enfant

    def sortie(ident):
        return Source.fromChildOutput(ident, "OUTPUT")

    source, table = Source.fromModelParameter("source"), Source.fromModelParameter("correspondances")
    etapes = [
        etape("filtre_lampes", "native:extractbyexpression", "Correspondances : type de lampe", 480, 170, INPUT=table,
              EXPRESSION="\"source\" = 'nantes' AND \"champ_source\" = 'type_de_lampe' AND \"attribut_cible\" = 'type_source'"),
        etape("filtre_supports", "native:extractbyexpression", "Correspondances : nature du support", 760, 170, INPUT=table,
              EXPRESSION="\"source\" = 'nantes' AND \"champ_source\" = 'nature_du_support' AND \"attribut_cible\" = 'type_support'"),
        etape("lampes", "native:joinattributestable", "Convertir le type de lampe", 100, 280, INPUT=source, FIELD="Type de lampe",
              INPUT_2=sortie("filtre_lampes"), FIELD_2="valeur_source", FIELDS_TO_COPY=["valeur_cible"], METHOD=1, PREFIX="lampe_"),
        etape("supports", "native:joinattributestable", "Convertir la nature du support", 100, 390, INPUT=sortie("lampes"), FIELD="Nature du support",
              INPUT_2=sortie("filtre_supports"), FIELD_2="valeur_source", FIELDS_TO_COPY=["valeur_cible"], METHOD=1, PREFIX="support_"),
        etape("position", "native:geometrybyexpression", "Lire la position dans Geolocalisation", 100, 500, INPUT=sortie("supports"), OUTPUT_GEOMETRY=2,
              WITH_Z=False, WITH_M=False,
              EXPRESSION='make_point(to_real(trim(string_to_array("Geolocalisation", \',\')[1])), to_real(trim(string_to_array("Geolocalisation", \',\')[0])))'),
        etape("wgs84", "native:assignprojection", "Déclarer le WGS 84", 100, 610, INPUT=sortie("position"), CRS="EPSG:4326"),
        etape("lambert", "native:reprojectlayer", "Passer en Lambert 93", 100, 720, INPUT=sortie("wgs84"), TARGET_CRS="EPSG:2154"),
        etape("attributs", "native:refactorfields", "Écrire les attributs du standard", 100, 830, INPUT=sortie("lambert"),
              FIELDS_MAPPING=[{"name": nom, "expression": expression, "type": type_champ, "length": 0, "precision": 0}
                              for nom, expression, type_champ in ATTRIBUTS]),
    ]
    resultat = QgsProcessingModelOutput(SORTIE_MODELE)
    resultat.setChildId("attributs")
    resultat.setChildOutputName("OUTPUT")
    resultat.setPosition(QPointF(380, 940))
    etapes[-1].setModelOutputs({SORTIE_MODELE: resultat})
    for enfant in etapes:
        modele.addChildAlgorithm(enfant)
    modele.updateDestinationParameters()
    MODELE.parent.mkdir(exist_ok=True)
    assert modele.toFile(str(MODELE)), "écriture du modèle impossible"
    return modele


def executer():
    """Relit le modèle depuis son fichier, comme un utilisateur, et l'exécute sur la dernière collecte."""
    import processing

    origine = max(d for d in (config.SOURCES / "nantes").iterdir() if (d / "manifeste.json").exists())
    nom_fichier = json.loads((origine / "manifeste.json").read_text(encoding="utf-8"))["fichier"]
    uri = f"file:///{(origine / nom_fichier).as_posix()}?delimiter=;&detectTypes=no&geomType=none"
    table = f"file:///{(config.CORRESPONDANCES / 'correspondances.csv').as_posix()}?delimiter=;&detectTypes=no&geomType=none"
    couches = {"source": QgsVectorLayer(uri, "source", "delimitedtext"), "correspondances": QgsVectorLayer(table, "correspondances", "delimitedtext")}
    assert all(c.isValid() for c in couches.values())
    QgsProject.instance().addMapLayers(list(couches.values()))

    modele = QgsProcessingModelAlgorithm()
    assert modele.fromFile(str(MODELE))
    contexte = QgsProcessingContext()
    contexte.setProject(QgsProject.instance())
    resultat = processing.run(modele, {"source": couches["source"], "correspondances": couches["correspondances"],
                                       f"attributs:{SORTIE_MODELE}": "memory:"}, context=contexte, feedback=QgsProcessingFeedback())
    return comparer(resultat[f"attributs:{SORTIE_MODELE}"])  # ici : la couche appartient au contexte, qui disparaît avec la fonction


def comparer(couche):
    with psycopg2.connect(host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB, user=config.PG_SUPERUSER) as c, c.cursor() as cur:
        cur.execute("""SELECT identifiant, "typeSource", support, puissance, "temperatureCouleur", ST_X(geometrie), ST_Y(geometrie)
                       FROM eclext.pointlumineux WHERE gestionnaire = 'NANTES'""")
        base = {ligne[0]: ligne for ligne in cur.fetchall()}
    modele, vus = {}, {}
    for f in couche.getFeatures():
        vus[f["identifiant"]] = vus.get(f["identifiant"], 0) + 1
        modele[f["identifiant"]] = f
    partages = sorted(k for k, n in vus.items() if n > 1)  # la voie SQL les distingue par un suffixe -D2
    differences = {"typeSource": 0, "support": 0, "puissance": 0, "temperatureCouleur": 0}
    renseignes = dict.fromkeys(differences, 0)  # zéro différence ne vaut que si des valeurs ont vraiment été comparées
    exemples, ecart_max, comparees = [], 0.0, 0
    for code, f in modele.items():
        if code in partages:
            continue
        ligne = base[code]
        comparees += 1
        for i, attribut in enumerate(differences, start=1):
            a, b = ligne[i], f[attribut]
            a, b = (None if v in (None, "") or v != v else v for v in (a, b))
            b = None if isinstance(b, QVariant) and b.isNull() else b
            renseignes[attribut] += a is not None and a != "XX"
            egal =(a is None and b is None) or (a is not None and b is not None and (str(a) == str(b) or (attribut in ("puissance", "temperatureCouleur") and float(a) == float(b))))
            if not egal:
                differences[attribut] += 1
                if len(exemples) < 8:
                    exemples.append([code, attribut, str(a), str(b)])
        point = f.geometry().asPoint()
        ecart_max = max(ecart_max, math.hypot(point.x() - ligne[5], point.y() - ligne[6]))
    return {"lignes_modele": couche.featureCount(), "objets_compares": comparees, "identifiants_partages_ecartes": len(partages),
            "absents_de_la_base": sum(1 for k in modele if k not in partages and k not in base),
            "valeurs_renseignees": renseignes, "differences": differences, "exemples": exemples, "ecart_position_max_m": round(ecart_max, 6)}


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    sys.path.append(str(config.QGIS_PYTHON.parents[1] / "apps" / "qgis-ltr" / "python" / "plugins"))
    from processing.core.Processing import Processing
    from qgis.analysis import QgsNativeAlgorithms

    Processing.initialize()
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    try:
        construire()
        bilan = executer()
        RESULTAT.parent.mkdir(parents=True, exist_ok=True)
        RESULTAT.write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(bilan, ensure_ascii=False), flush=True)
    except Exception:
        traceback.print_exc()  # os._exit ci-dessous effacerait l'erreur
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)  # Processing plante souvent à la fermeture d'un script autonome, une fois le travail fini
