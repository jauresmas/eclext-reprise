"""Vérifie les projets QGIS en les rouvrant, avec le compte de chaque profil. Écrit un JSON de résultats.

Script du Python de QGIS, lancé par tests/test_8_qgis.py :
    python-qgis-ltr.bat tests/qgis_projets.py sortie.json
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import config  # noqa: E402
import psycopg2  # noqa: E402
from qgis.core import (QgsApplication, QgsExpression, QgsExpressionContext, QgsExpressionContextScope, QgsExpressionContextUtils,  # noqa: E402
                       QgsFeatureRequest, QgsFieldConstraints, QgsGeometry, QgsProject, QgsVectorDataProvider, QgsVectorLayerUtils)

ATTENDU_POINTS = {"administrateur": None, "collectivite": ["44143"], "entreprise": ["44143", "44020"]}
MARQUE = "Essai automatique de la recette, à effacer"


def compter(requete, *parametres):
    with psycopg2.connect(host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB, user=config.PG_SUPERUSER) as c:
        with c.cursor() as cur:
            cur.execute(requete, parametres)
            return cur.fetchone()[0]


def nettoyer():
    with psycopg2.connect(host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB, user=config.PG_SUPERUSER) as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM exploitation.signalement WHERE description = %s", (MARQUE,))
            cur.execute("DELETE FROM audit.journal WHERE avant ->> 'description' = %s OR apres ->> 'description' = %s", (MARQUE, MARQUE))


def erreurs(couche, entite):
    return [champ.name() for i, champ in enumerate(couche.fields())
            if not QgsVectorLayerUtils.validateAttribute(couche, entite, i, QgsFieldConstraints.ConstraintStrengthHard)[0]]


def peut(couche, capacite):
    return bool(couche.dataProvider().capabilities() & capacite)


def verifier(profil):
    r = {}
    projet = QgsProject.instance()
    r["lecture"] = projet.read(str(config.RACINE / "projets" / f"eclairage_{profil}.qgz"))
    couches = {c.name(): c for c in projet.mapLayers().values()}
    r["couches_invalides"] = [nom for nom, c in couches.items() if not c.isValid() and nom != "Plan IGN"]
    r["sans_mot_de_passe"] = all("password" not in c.source() for c in couches.values())
    r["relations"] = sorted(n for n, x in projet.relationManager().relations().items() if x.isValid())
    r["themes"] = sorted(projet.mapThemeCollection().mapThemes())
    point, signalement, intervention = couches["Points lumineux"], couches["Signalements"], couches["Interventions"]

    r["points_vus"] = sum(1 for _ in point.getFeatures(QgsFeatureRequest().setNoAttributes().setFlags(QgsFeatureRequest.NoGeometry)))
    r["communes_vues"] = sorted(set(point.uniqueValues(point.fields().indexOf("insee"))))[:5]
    r["interventions_vues"] = sum(1 for _ in intervention.getFeatures())
    r["signalements_vus"] = sum(1 for _ in signalement.getFeatures())

    capacites = {"Ajouter": QgsVectorDataProvider.AddFeatures, "Modifier": QgsVectorDataProvider.ChangeAttributeValues,
                 "Supprimer": QgsVectorDataProvider.DeleteFeatures}
    r["droits"] = {nom: sorted(k for k, cap in capacites.items() if peut(couches[nom], cap))
                   for nom in ["Points lumineux", "Supports", "Armoires", "Signalements", "Interventions"]}

    r["onglets"] = {nom: [o.name() for o in couches[nom].editFormConfig().tabs()]
                    for nom in ["Armoires", "Supports", "Points lumineux", "Signalements", "Interventions"]}
    r["actions"] = {nom: [a.name() for a in couches[nom].actions().actions()] for nom in ["Points lumineux", "Signalements"]}

    # Dossier des photos de terrain : l'expression de la fiche, évaluée avec la vraie variable du projet ouvert,
    # puis avec le même chemin que QGIS donnerait depuis projets/mon_postgres/ (mêmes séparateurs)
    reglage = signalement.editorWidgetSetup(signalement.fields().indexOf("photo"))
    racine = reglage.config()["PropertyCollection"]["properties"]["propertyRootPath"]["expression"]
    r["photo_terrain"] = {"widget": reglage.type()}
    dossier = QgsExpressionContextUtils.projectScope(projet).variable("project_folder")
    separateur = "\\" if "\\" in dossier else "/"
    for cle, chemin in {"projets": dossier, "mon_postgres": dossier + separateur + "mon_postgres"}.items():
        contexte = QgsExpressionContext()
        portee = QgsExpressionContextScope()
        portee.setVariable("project_folder", chemin)
        contexte.appendScope(portee)
        r["photo_terrain"][cle] = QgsExpression(racine).evaluate(contexte)

    # Recherches enregistrées : toutes doivent s'exécuter sur la base, sans erreur
    r["recherches"] = {}
    r["recherches_en_erreur"] = []
    for nom in ["Armoires", "Supports", "Points lumineux", "Signalements", "Interventions", "Écarts de contrôle"]:
        couche = couches.get(nom)
        if couche is None:
            continue
        for stockee in couche.storedExpressionManager().storedExpressions():
            requete = QgsFeatureRequest(QgsExpression(stockee.expression)).setNoAttributes().setFlags(QgsFeatureRequest.NoGeometry)
            iterateur = couche.getFeatures(requete)
            r["recherches"][f"{nom} / {stockee.name}"] = sum(1 for _ in iterateur)
            if iterateur.compileFailed() and QgsExpression(stockee.expression).hasParserError():
                r["recherches_en_erreur"].append(stockee.name)
    r["affichage_invalide"] = [nom for nom in ["Armoires", "Supports", "Points lumineux", "Signalements", "Interventions"]
                               if QgsExpression(couches[nom].displayExpression()).hasParserError()]
    r["non_cherchables"] = [c.name() for c in couches.values()
                            if c.type() == 0 and not (c.flags() & c.Searchable)]

    # Contraintes du formulaire d'intervention : saisies volontairement fausses
    entite = next(intervention.getFeatures("\"etat\" = 'EN_COURS'"), None)
    r["contraintes"] = {}
    if entite is not None:
        entite["etat"] = "REALISEE"
        entite["date_realisee"] = None
        entite["compte_rendu"] = None
        r["contraintes"]["realisee_sans_date_ni_compte_rendu"] = sorted(set(erreurs(intervention, entite)) & {"date_realisee", "compte_rendu"})
        entite["date_realisee"] = "2099-01-01"
        entite["compte_rendu"] = "Fait"
        r["contraintes"]["date_dans_le_futur"] = sorted(set(erreurs(intervention, entite)) & {"date_realisee"})
        entite["nature"] = "REMPLACEMENT_SOURCE"
        entite["date_realisee"] = "2026-01-01"
        r["contraintes"]["changement_sans_nouveau_materiel"] = sorted(set(erreurs(intervention, entite)) & {"nouveau_type_source", "nouvelle_puissance_w"})

    # Écriture à travers QGIS, avec le compte du profil
    r["signaler_sur_son_perimetre"] = r["signaler_hors_perimetre"] = None
    if profil == "collectivite":
        cible = next(point.getFeatures())
        for cle, point_id, geometrie, insee in [("signaler_sur_son_perimetre", cible["id"], cible.geometry(), cible["insee"]),
                                                ("signaler_hors_perimetre", compter("SELECT min(id) FROM metier.point_lumineux WHERE insee = '44215'"),
                                                 QgsGeometry.fromWkt("Point (0 0)"), "44215")]:
            signalement.startEditing()
            f = QgsVectorLayerUtils.createFeature(signalement, geometrie, {
                signalement.fields().indexOf("point_id"): point_id, signalement.fields().indexOf("insee"): insee,
                signalement.fields().indexOf("nature"): "PANNE", signalement.fields().indexOf("statut"): "OUVERT",
                signalement.fields().indexOf("description"): MARQUE})
            signalement.addFeature(f)
            accepte = signalement.commitChanges()
            r[cle] = accepte
            if not accepte:
                signalement.rollBack()
        r["signalement_ecrit_en_base"] = compter("SELECT count(*) FROM exploitation.signalement WHERE description = %s", MARQUE)
        r["declarant_en_base"] = compter("SELECT max(declarant) FROM exploitation.signalement WHERE description = %s", MARQUE)
        r["statut_en_base"] = compter("SELECT max(statut) FROM exploitation.signalement WHERE description = %s", MARQUE)
        nettoyer()

    if profil == "entreprise":
        cible = next(intervention.getFeatures("\"etat\" = 'A_PLANIFIER' AND \"date_prevue\" IS NOT NULL"))
        intervention.startEditing()
        intervention.changeAttributeValue(cible.id(), intervention.fields().indexOf("nature"), "CONTROLE")
        r["changer_la_nature"] = intervention.commitChanges()
        if not r["changer_la_nature"]:
            intervention.rollBack()
        intervention.startEditing()
        intervention.changeAttributeValue(cible.id(), intervention.fields().indexOf("etat"), "REALISEE")
        r["sauter_des_etats"] = intervention.commitChanges()
        if not r["sauter_des_etats"]:
            intervention.rollBack()

    projet.clear()
    return r


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        nettoyer()
        resultats = {profil: verifier(profil) for profil in ATTENDU_POINTS}
        Path(sys.argv[1]).write_text(json.dumps(resultats, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    finally:
        sys.stdout.flush()
        os._exit(0)
