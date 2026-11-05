"""Étape 8 : projets QGIS de consultation et de saisie, un par profil.

    projets/eclairage_administrateur.qgz   tout le territoire, patrimoine, exploitation, contrôle
    projets/eclairage_collectivite.qgz     une commune : consulter, signaler une panne
    projets/eclairage_entreprise.qgz       son périmètre : tenir à jour ses interventions

Chaque projet se connecte avec le compte de son profil : ce que l'utilisateur voit et peut modifier
vient de la base (rôles et sécurité au niveau des lignes, sql/41_roles.sql), pas du projet.

    python-qgis-ltr.bat 08_projets_qgis.py
"""
import faulthandler
from urllib.parse import quote

import config
from qgis.core import (Qgis, QgsAction, QgsApplication, QgsAttributeEditorContainer, QgsAttributeEditorField,
                       QgsAttributeEditorRelation, QgsCoordinateReferenceSystem, QgsDataSourceUri, QgsDatumTransform,
                       QgsDefaultValue, QgsEditFormConfig, QgsEditorWidgetSetup, QgsFieldConstraints, QgsFillSymbol, QgsLayerTreeModel,
                       QgsMapLayer, QgsMapThemeCollection, QgsMarkerSymbol, QgsOptionalExpression, QgsExpression,
                       QgsPalLayerSettings, QgsProject, QgsRasterLayer, QgsRectangle, QgsReferencedRectangle,
                       QgsRelation, QgsRuleBasedRenderer, QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling, QgsWkbTypes)
from qgis.PyQt.QtGui import QColor, QFont

faulthandler.enable()

DUR = QgsFieldConstraints.ConstraintStrengthHard
SORTIE = config.RACINE / "projets"

PROFILS = {
    "administrateur": ("demo_admin", "Éclairage extérieur : administration"),
    "collectivite": ("demo_commune", "Éclairage extérieur : collectivité"),
    "entreprise": ("demo_entreprise", "Éclairage extérieur : entreprise de maintenance"),
}
COMMUNE_DEMO = "44143"

LISTES = [("ref", "usage"), ("ref", "type_source"), ("ref", "structure_luminaire"), ("ref", "support_luminaire"),
          ("ref", "eclairage_adaptatif"), ("ref", "statut_installation"), ("ref", "etat_support"), ("ref", "type_pose"),
          ("ref", "type_massif"), ("ref", "classe_precision"), ("ref", "proprietaire"), ("ref", "nature_signalement"),
          ("ref", "statut_signalement"), ("ref", "nature_intervention"), ("ref", "etat_intervention")]

ALIAS = {
    "armoire": {"code": "Armoire", "code_source": "Code d'origine", "insee": "Commune", "exploitant": "Exploitant",
                "position_estimee": "Position estimée", "maj_locale": "Modifiée après la reprise", "gestionnaire_id": "Gestionnaire", "lot_id": "Lot source",
                "retire_le": "Retirée de la source le"},
    "support": {"code": "Support", "insee": "Commune", "armoire_id": "Armoire", "voie": "Voie", "quartier": "Quartier",
                "type_support": "Type de support", "hauteur_m": "Hauteur (m)", "saillie_m": "Saillie (m)", "nature": "Matériau",
                "forme": "Forme", "couleur": "Couleur", "marque": "Marque", "etat": "État", "type_pose": "Pose du réseau",
                "type_massif": "Massif", "dimension_massif": "Dimensions du massif", "entraxe": "Entraxe",
                "presence_terre": "Terre présente", "prise_illumination": "Prise d'illumination", "autonome": "Autonome",
                "date_pose": "Date de pose", "proprietaire": "Propriétaire", "competence_transferee": "Compétence transférée",
                "type_maintenance": "Type de maintenance", "exploitant": "Exploitant", "classe_precision": "Classe de précision",
                "z_m": "Altitude (m)", "observation": "Observation", "maj_locale": "Modifié après la reprise", "gestionnaire_id": "Gestionnaire", "lot_id": "Lot source",
                "ligne_source": "Ligne de la source", "retire_le": "Retiré de la source le"},
    "point": {"code": "Point lumineux", "support_id": "Support", "depart_id": "Départ", "insee": "Commune", "statut": "Statut",
              "eclairage_public": "Éclairage public", "usage": "Usage de la voie", "type_source": "Type de source",
              "structure": "Structure du luminaire", "temperature_couleur": "Température de couleur (K)",
              "puissance_w": "Puissance (W)", "valide_de": "Matériel valide depuis", "valide_jusque": "Valide jusqu'au",
              "extinction_nuit": "Extinction de nuit", "est_adaptatif": "Éclairage adaptatif",
              "eclairage_adaptatif": "Type d'adaptation", "profil_nocturne": "Profil nocturne", "fabricant": "Fabricant",
              "modele": "Modèle", "photometrie": "Photométrie", "hauteur_feu_m": "Hauteur de feu (m)",
              "flux_source_lm": "Flux de la source (lm)", "flux_luminaire_lm": "Flux du luminaire (lm)", "cie3": "CIE 3",
              "ulr_nominal": "ULR nominal", "ulr_installe": "ULR installé", "inclinaison_max": "Inclinaison maximale",
              "inclinaison_installee": "Inclinaison installée", "date_premiere_installation": "Première installation",
              "nb_sources": "Nombre de sources", "designation_lampe": "Désignation de la lampe",
              "un_point_par_support": "Hypothèse un point par support", "maj_locale": "Modifié après la reprise",
              "gestionnaire_id": "Gestionnaire", "lot_id": "Lot source", "ligne_source": "Ligne de la source",
              "retire_le": "Retiré de la source le"},
    "signalement": {"point_id": "Point lumineux", "support_id": "Support", "insee": "Commune", "nature": "Nature",
                    "statut": "Statut", "declare_le": "Déclaré le", "declarant": "Déclarant", "description": "Description",
                    "jeu_essai": "Jeu d'essai", "constate_le": "Constaté sur place le", "photo": "Photo"},
    "intervention": {"signalement_id": "Signalement", "point_id": "Point lumineux", "support_id": "Support",
                     "armoire_id": "Armoire", "insee": "Commune", "entreprise_id": "Entreprise", "nature": "Nature",
                     "etat": "État", "date_prevue": "Date prévue", "date_realisee": "Date de réalisation",
                     "compte_rendu": "Compte rendu", "nouveau_type_source": "Nouveau type de source",
                     "nouvelle_puissance_w": "Nouvelle puissance (W)", "nouvelle_temperature": "Nouvelle température (K)",
                     "cree_le": "Créée le", "cree_par": "Créée par", "jeu_essai": "Jeu d'essai"},
    "ecart": {"regle": "Règle", "gestionnaire_id": "Gestionnaire", "code_objet": "Objet", "insee": "Commune",
              "valeur_lue": "Valeur lue", "valeur_retenue": "Valeur retenue", "mesure": "Mesure", "decision": "Décision",
              "commentaire": "Commentaire", "traite_par": "Traité par", "traite_le": "Traité le", "table_objet": "Table",
              "objet_id": "Identifiant de l'objet"},
}

# Colonnes techniques exclues de la recherche par la barre de localisation
NON_CHERCHEES = ["id", "gestionnaire_id", "lot_id", "ligne_source", "support_id", "depart_id", "armoire_id", "objet_id", "nb_sources"]

REGLES_SOURCE = [("Diodes électroluminescentes", "\"type_source\" = 'LED'", "#1a9850"),
                 ("Sodium haute pression", "\"type_source\" = 'SHP'", "#f28e2b"),
                 ("Sodium basse pression", "\"type_source\" = 'SBP'", "#e8c14a"),
                 ("Iodures métalliques", "\"type_source\" = 'IM'", "#7b5ea7"),
                 ("Vapeur de mercure", "\"type_source\" = 'VM'", "#d7301f"),
                 ("Fluorescence, halogène, autres", "\"type_source\" NOT IN ('LED', 'SHP', 'SBP', 'IM', 'VM', 'XX', 'AU')", "#4c78a8"),
                 ("Non renseigné", "\"type_source\" IN ('XX', 'AU')", "#9a9a9a")]

# Le dossier des photos se déduit de celui du projet : l'expression vaut dans projets/ comme dans projets/mon_postgres/.
# Sous Windows, @project_folder arrive avec des antislashs : on les remplace avant de chercher le dossier.
RACINE_PHOTOS = "regexp_replace(replace(@project_folder, '\\\\', '/'), '/projets(/mon_postgres)?$', '') || '/data/terrain/photos'"


def fond_ign():
    """Fond de plan IGN (Géoplateforme, licence ouverte) ; le projet reste lisible sans réseau."""
    tuile = ("SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
             "&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}")
    # Le « ? » reste en clair : encodé, QGIS ne reçoit aucune tuile, sans message d'erreur
    fond = QgsRasterLayer("type=xyz&zmin=0&zmax=19&url=https://data.geopf.fr/wmts?" + quote(tuile, safe="/{}"), "Plan IGN", "wms")
    assert fond.isValid(), "fond de plan invalide"
    return fond


def idx(lyr, champ):
    i = lyr.fields().indexOf(champ)
    assert i >= 0, f"{lyr.name()} : champ {champ} absent"
    return i


def alias(lyr, cle):
    for champ, libelle in ALIAS[cle].items():
        lyr.setFieldAlias(idx(lyr, champ), libelle)


def liste(lyr, champ, ref, cle="code", valeur="description", nulle=True):
    lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("ValueRelation", {
        "Layer": ref.id(), "LayerName": ref.name(), "LayerProviderName": "postgres", "LayerSource": ref.source(),
        "Key": cle, "Value": valeur, "AllowNull": nulle, "AllowMulti": False, "OrderByValue": True, "UseCompleter": False,
        "NofColumns": 1, "FilterExpression": ""}))


def date(lyr, *champs):
    for champ in champs:
        lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("DateTime", {
            "display_format": "dd/MM/yyyy", "field_format": "yyyy-MM-dd", "calendar_popup": True, "allow_null": True,
            "field_iso_format": False}))


def horodatage(lyr, *champs):
    for champ in champs:
        lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("DateTime", {
            "display_format": "dd/MM/yyyy HH:mm", "field_format": "yyyy-MM-dd HH:mm:ss", "calendar_popup": False,
            "allow_null": True, "field_iso_format": False}))


def booleens(lyr, *champs):
    for champ in champs:
        lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("CheckBox", {"AllowNullState": True}))


def texte_long(lyr, *champs):
    for champ in champs:
        lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("TextEdit", {"IsMultiline": True, "UseHtml": False}))


def photo_en_lecture(lyr, champ, racine):
    """Image affichée dans la fiche ; la base ne garde que le nom du fichier, le dossier vient de l'expression."""
    lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("ExternalResource", {
        "DocumentViewer": 1, "DocumentViewerHeight": 320, "DocumentViewerWidth": 0, "FileWidget": False, "FileWidgetButton": False,
        "RelativeStorage": 2, "UseLink": False, "FullUrl": False,
        "PropertyCollection": {"name": None, "type": "collection",
                               "properties": {"propertyRootPath": {"active": True, "type": 3, "expression": racine}}}}))


def masque(lyr, *champs):
    for champ in champs:
        lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("Hidden", {}))


def reference(lyr, champ, relation, lecture=False):
    lyr.setEditorWidgetSetup(idx(lyr, champ), QgsEditorWidgetSetup("RelationReference", {
        "Relation": relation.id(), "AllowNULL": True, "ShowForm": False, "ShowOpenFormButton": True, "MapIdentification": not lecture,
        "ReadOnly": lecture, "OrderByValue": False, "AllowAddFeatures": False}))


def contrainte(lyr, champ, expression, message):
    i = idx(lyr, champ)
    lyr.setConstraintExpression(i, expression, message)
    lyr.setFieldConstraint(i, QgsFieldConstraints.ConstraintExpression, DUR)


def defaut(lyr, champ, expression):
    lyr.setDefaultValueDefinition(idx(lyr, champ), QgsDefaultValue(expression))


def lecture_seule(lyr, *champs):
    fc = lyr.editFormConfig()
    for champ in champs:
        fc.setReadOnly(idx(lyr, champ), True)
    lyr.setEditFormConfig(fc)


def onglets(lyr, structure):
    """structure : [(titre, contenu[, visibilité])] ; contenu = liste de champs, de QgsRelation, ou de (titre, champs, visibilité)."""
    fc = lyr.editFormConfig()
    fc.setLayout(QgsEditFormConfig.TabLayout)
    racine = fc.invisibleRootContainer()
    racine.clear()
    for titre, contenu, *visible in structure:
        onglet = QgsAttributeEditorContainer(titre, racine)
        onglet.setType(Qgis.AttributeEditorContainerType.Tab)
        onglet.setColumnCount(1)
        if visible:
            onglet.setVisibilityExpression(QgsOptionalExpression(QgsExpression(visible[0])))
        for element in contenu:
            if isinstance(element, str):
                onglet.addChildElement(QgsAttributeEditorField(element, idx(lyr, element), onglet))
            elif isinstance(element, QgsRelation):
                onglet.addChildElement(QgsAttributeEditorRelation(element, onglet))
            else:
                sous_titre, champs, visible = element
                bloc = QgsAttributeEditorContainer(sous_titre, onglet)
                bloc.setType(Qgis.AttributeEditorContainerType.GroupBox)
                bloc.setVisibilityExpression(QgsOptionalExpression(QgsExpression(visible)))
                for champ in champs:
                    bloc.addChildElement(QgsAttributeEditorField(champ, idx(lyr, champ), bloc))
                onglet.addChildElement(bloc)
        racine.addChildElement(onglet)
    lyr.setEditFormConfig(fc)


def recherches(lyr, enregistrees):
    for nom, expression in enregistrees.items():
        lyr.storedExpressionManager().addStoredExpression(nom, expression)


def non_cherchables(lyr):
    for champ in NON_CHERCHEES:
        i = lyr.fields().indexOf(champ)
        if i >= 0:
            lyr.setFieldConfigurationFlag(i, Qgis.FieldConfigurationFlag.NotSearchable, True)


def regles(lyr, definition, taille=2.0, forme="circle", contour="#ffffff"):
    racine = QgsRuleBasedRenderer.Rule(None)
    for libelle, expression, couleur, *echelle in definition:
        # Une croix n'a pas de remplissage : seule la couleur de son trait se voit
        trait = {"outline_color": couleur, "outline_width": "0.45"} if forme == "cross2" else {"outline_color": contour, "outline_width": "0.15"}
        symbole = QgsMarkerSymbol.createSimple({"name": forme, "color": couleur, "size": str(taille), **trait})
        racine.appendChild(QgsRuleBasedRenderer.Rule(symbole, 0, echelle[0] if echelle else 0, expression, libelle))
    lyr.setRenderer(QgsRuleBasedRenderer(racine))


def etiquettes(lyr, expression, echelle, taille=8, couleur="#222222"):
    format_texte = QgsTextFormat()
    format_texte.setFont(QFont("Segoe UI"))
    format_texte.setSize(taille)
    format_texte.setColor(QColor(couleur))
    tampon = QgsTextBufferSettings()
    tampon.setEnabled(True)
    tampon.setSize(0.7)
    tampon.setColor(QColor("#ffffff"))
    format_texte.setBuffer(tampon)
    reglage = QgsPalLayerSettings()
    reglage.fieldName = expression
    reglage.isExpression = True
    reglage.setFormat(format_texte)
    reglage.scaleVisibility = True
    reglage.minimumScale = echelle
    reglage.maximumScale = 0
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(reglage))
    lyr.setLabelsEnabled(True)


def echelle_max(lyr, denominateur):
    lyr.setScaleBasedVisibility(True)
    lyr.setMinimumScale(denominateur)
    lyr.setMaximumScale(0)


ACTION_SIGNALER = """from qgis.core import QgsGeometry, QgsProject
from qgis.utils import iface
couche = QgsProject.instance().mapLayersByName('Signalements')[0]
valeurs = {couche.fields().indexOf('point_id'): [% "id" %], couche.fields().indexOf('insee'): '[% "insee" %]'}
couche.startEditing()
if iface.vectorLayerTools().addFeature(couche, valeurs, QgsGeometry.fromWkt('[% geom_to_wkt($geometry) %]')):
    if not couche.commitChanges():
        iface.messageBar().pushCritical('Signalement refusé', ' ; '.join(couche.commitErrors()))
        couche.rollBack()
else:
    couche.rollBack()
"""

ACTION_INTERVENTION = """from qgis.core import QgsGeometry, QgsProject
from qgis.utils import iface
couche = QgsProject.instance().mapLayersByName('Interventions')[0]
valeurs = {couche.fields().indexOf('point_id'): [% "point_id" %], couche.fields().indexOf('insee'): '[% "insee" %]',
           couche.fields().indexOf('signalement_id'): [% "id" %]}
couche.startEditing()
if iface.vectorLayerTools().addFeature(couche, valeurs, QgsGeometry.fromWkt('[% geom_to_wkt($geometry) %]')):
    if not couche.commitChanges():
        iface.messageBar().pushCritical('Intervention refusée', ' ; '.join(couche.commitErrors()))
        couche.rollBack()
else:
    couche.rollBack()
"""

VUE_IMMERSIVE = ("https://www.google.com/maps/@?api=1&map_action=pano&viewpoint="
                 "[% y(transform($geometry, 'EPSG:2154', 'EPSG:4326')) %],[% x(transform($geometry, 'EPSG:2154', 'EPSG:4326')) %]")


def action(lyr, type_action, nom, commande):
    a = QgsAction(type_action, nom, commande)
    a.setActionScopes({"Feature", "Canvas"})
    lyr.actions().addAction(a)


def construire(profil):
    login, titre = PROFILS[profil]
    admin = profil == "administrateur"
    entreprise = profil == "entreprise"
    projet = QgsProject.instance()
    projet.clear()
    projet.setTitle(titre)
    crs = QgsCoordinateReferenceSystem("EPSG:2154")
    projet.setCrs(crs)
    projet.setFileName(str(SORTIE / f"eclairage_{profil}.qgz"))

    def pg(schema, table, nom, cle, geom=None):
        uri = QgsDataSourceUri()
        uri.setConnection(config.PG_HOST, str(config.PG_PORT), config.PG_DB, login, "")
        uri.setDataSource(schema, table, geom, "", cle)
        if geom:
            uri.setSrid("2154")
            uri.setWkbType(QgsWkbTypes.MultiPolygon if table == "commune" else QgsWkbTypes.Point)
        uri.setUseEstimatedMetadata(True)
        lyr = QgsVectorLayer(uri.uri(False), nom, "postgres")
        assert lyr.isValid(), f"{schema}.{table} ({login}) : {lyr.error().message()}"
        projet.addMapLayer(lyr, False)
        return lyr

    armoire = pg("metier", "armoire", "Armoires", "id", "geom")
    support = pg("metier", "support", "Supports", "id", "geom")
    point = pg("metier", "point_lumineux", "Points lumineux", "id", "geom")
    signalement = pg("exploitation", "signalement", "Signalements", "id", "geom")
    intervention = pg("exploitation", "intervention", "Interventions", "id", "geom")
    commune = pg("ref", "commune", "Communes", "insee", "geom")
    gestionnaire = pg("metier", "gestionnaire", "Gestionnaires", "id")
    societe = pg("admin", "entreprise", "Entreprises", "id")
    ref = {table: pg(schema, table, table.replace("_", " ").capitalize(), "code") for schema, table in LISTES}
    ecart = regle = None
    if not entreprise:
        ecart = pg("controle", "ecart", "Écarts de contrôle", "id", "geom")
        regle = pg("controle", "regle", "Règles de contrôle", "code")
    listes = list(ref.values()) + [gestionnaire, societe] + ([regle] if regle else [])

    fond = fond_ign()
    projet.addMapLayer(fond, False)
    # Transformation fixée dans le projet : QGIS ne pose pas la question à l'ouverture
    mercator = QgsCoordinateReferenceSystem("EPSG:3857")
    contexte = projet.transformContext()
    contexte.addCoordinateOperation(crs, mercator, QgsDatumTransform.operations(crs, mercator)[0].proj, True)
    projet.setTransformContext(contexte)

    # Relations entre fiches -------------------------------------------------------------------
    def relation(ident, nom, fille, champ, mere, cle="id"):
        r = QgsRelation()
        r.setId(ident)
        r.setName(nom)
        r.setReferencingLayer(fille.id())
        r.setReferencedLayer(mere.id())
        r.addFieldPair(champ, cle)
        assert r.isValid(), f"relation {ident} invalide"
        projet.relationManager().addRelation(r)
        return r

    rel_armoire = relation("rel_armoire_supports", "Supports de l'armoire", support, "armoire_id", armoire)
    rel_support = relation("rel_support_points", "Points lumineux du support", point, "support_id", support)
    rel_signalements = relation("rel_point_signalements", "Signalements du point", signalement, "point_id", point)
    rel_interventions = relation("rel_point_interventions", "Interventions sur le point", intervention, "point_id", point)
    rel_suite = relation("rel_signalement_interventions", "Interventions du signalement", intervention, "signalement_id", signalement)

    # Fiche armoire ----------------------------------------------------------------------------
    alias(armoire, "armoire")
    liste(armoire, "insee", commune, "insee", "nom")
    liste(armoire, "gestionnaire_id", gestionnaire, "id", "code")
    booleens(armoire, "position_estimee", "maj_locale")
    date(armoire, "retire_le")
    masque(armoire, "id")
    onglets(armoire, [("Armoire", ["code", "insee", "exploitant", "position_estimee", "gestionnaire_id"]),
                      ("Supports raccordés", [rel_armoire]),
                      ("Origine", ["code_source", "maj_locale", "lot_id", "retire_le"])])
    armoire.setDisplayExpression("\"code\" || coalesce(' (' || \"exploitant\" || ')', '')")
    lecture_seule(armoire, "code", "code_source", "maj_locale", "gestionnaire_id", "lot_id", "retire_le")
    recherches(armoire, {"Position estimée à partir des supports": '"position_estimee"',
                         "Modifiées après la reprise": '"maj_locale"',
                         "Retirées de la source": '"retire_le" IS NOT NULL'})

    # Fiche support ----------------------------------------------------------------------------
    alias(support, "support")
    liste(support, "insee", commune, "insee", "nom")
    liste(support, "gestionnaire_id", gestionnaire, "id", "code")
    liste(support, "type_support", ref["support_luminaire"], nulle=False)
    liste(support, "etat", ref["etat_support"])
    liste(support, "type_pose", ref["type_pose"])
    liste(support, "type_massif", ref["type_massif"])
    liste(support, "proprietaire", ref["proprietaire"])
    liste(support, "classe_precision", ref["classe_precision"])
    booleens(support, "presence_terre", "prise_illumination", "autonome", "competence_transferee", "maj_locale")
    date(support, "date_pose", "retire_le")
    texte_long(support, "observation")
    reference(support, "armoire_id", rel_armoire, lecture=not admin)
    masque(support, "id")
    contrainte(support, "hauteur_m", '"hauteur_m" IS NULL OR ("hauteur_m" > 0 AND "hauteur_m" <= 60)', "Hauteur comprise entre 0 et 60 m")
    contrainte(support, "saillie_m", '"saillie_m" IS NULL OR "saillie_m" BETWEEN 0 AND 20', "Saillie comprise entre 0 et 20 m")
    contrainte(support, "date_pose", '"date_pose" IS NULL OR "date_pose" <= now()', "La date de pose ne peut pas être dans le futur")
    onglets(support, [("Identification", ["code", "insee", "voie", "quartier", "armoire_id", "classe_precision", "z_m"]),
                      ("Mât", ["type_support", "hauteur_m", "saillie_m", "nature", "forme", "couleur", "marque", "etat"]),
                      ("Génie civil", ["type_pose", "type_massif", "dimension_massif", "entraxe", "presence_terre", "prise_illumination", "autonome"]),
                      ("Gestion", ["date_pose", "proprietaire", "competence_transferee", "type_maintenance", "exploitant", "observation"]),
                      ("Points lumineux", [rel_support]),
                      ("Origine", ["maj_locale", "gestionnaire_id", "lot_id", "ligne_source", "retire_le"])])
    support.setDisplayExpression("\"code\" || coalesce(', ' || \"voie\", '')")
    lecture_seule(support, "code", "maj_locale", "gestionnaire_id", "lot_id", "ligne_source", "retire_le")
    recherches(support, {"Sans armoire de rattachement": '"armoire_id" IS NULL',
                         "Modifiés après la reprise": '"maj_locale"',
                         "Hauteur non renseignée": '"hauteur_m" IS NULL',
                         "Propriété intercommunale": "\"proprietaire\" = 'EPCI'",
                         "Type de support non renseigné": "\"type_support\" IN ('XX', 'AU')"})

    # Fiche point lumineux ---------------------------------------------------------------------
    alias(point, "point")
    liste(point, "insee", commune, "insee", "nom", nulle=False)
    liste(point, "gestionnaire_id", gestionnaire, "id", "code")
    liste(point, "statut", ref["statut_installation"], nulle=False)
    liste(point, "usage", ref["usage"], nulle=False)
    liste(point, "type_source", ref["type_source"], nulle=False)
    liste(point, "structure", ref["structure_luminaire"], nulle=False)
    liste(point, "eclairage_adaptatif", ref["eclairage_adaptatif"])
    booleens(point, "eclairage_public", "extinction_nuit", "est_adaptatif", "un_point_par_support", "maj_locale")
    date(point, "valide_de", "valide_jusque", "date_premiere_installation", "retire_le")
    reference(point, "support_id", rel_support, lecture=True)
    masque(point, "id", "depart_id")
    contrainte(point, "temperature_couleur", '"temperature_couleur" IS NULL OR "temperature_couleur" BETWEEN 1000 AND 10000', "Température comprise entre 1 000 et 10 000 K")
    contrainte(point, "puissance_w", '"puissance_w" IS NULL OR "puissance_w" > 0', "La puissance doit être positive")
    contrainte(point, "hauteur_feu_m", '"hauteur_feu_m" IS NULL OR "hauteur_feu_m" BETWEEN 0 AND 60', "Hauteur de feu comprise entre 0 et 60 m")
    contrainte(point, "valide_de", '"valide_de" IS NULL OR "valide_de" <= now()', "La date ne peut pas être dans le futur")
    contrainte(point, "valide_jusque", '"valide_jusque" IS NULL OR "valide_de" IS NULL OR "valide_jusque" >= "valide_de"', "Fin de validité antérieure au début")
    onglets(point, [("Identification", ["code", "support_id", "insee", "statut", "eclairage_public", "usage"]),
                    ("Matériel", ["type_source", "structure", "temperature_couleur", "puissance_w", "nb_sources", "designation_lampe", "fabricant", "modele", "photometrie"]),
                    ("Photométrie", ["hauteur_feu_m", "flux_source_lm", "flux_luminaire_lm", "cie3", "ulr_nominal", "ulr_installe", "inclinaison_max", "inclinaison_installee"]),
                    ("Allumage", ["extinction_nuit", "profil_nocturne", "est_adaptatif", ("Adaptation", ["eclairage_adaptatif"], '"est_adaptatif"')]),
                    ("Signalements", [rel_signalements]),
                    ("Interventions", [rel_interventions]),
                    ("Validité et origine", ["valide_de", "valide_jusque", "date_premiere_installation", "maj_locale", "un_point_par_support", "gestionnaire_id", "lot_id", "ligne_source", "retire_le"])])
    point.setDisplayExpression("\"code\" || ', ' || \"type_source\" || coalesce(' ' || round(\"puissance_w\") || ' W', '')")
    lecture_seule(point, "code", "maj_locale", "un_point_par_support", "gestionnaire_id", "lot_id", "ligne_source", "retire_le")
    recherches(point, {"Sources à vapeur de mercure": "\"type_source\" = 'VM'",
                       "Diodes électroluminescentes": "\"type_source\" = 'LED'",
                       "Puissance supérieure à 150 W": '"puissance_w" > 150',
                       "Type de source non renseigné": "\"type_source\" IN ('XX', 'AU')",
                       "Modifiés après la reprise": '"maj_locale"'})
    if not entreprise:
        action(point, QgsAction.GenericPython, "Signaler une panne", ACTION_SIGNALER)
    action(point, QgsAction.OpenUrl, "Vue immersive", VUE_IMMERSIVE)

    # Fiche signalement ------------------------------------------------------------------------
    alias(signalement, "signalement")
    liste(signalement, "insee", commune, "insee", "nom", nulle=False)
    liste(signalement, "nature", ref["nature_signalement"], nulle=False)
    liste(signalement, "statut", ref["statut_signalement"], nulle=False)
    reference(signalement, "point_id", rel_signalements, lecture=True)
    horodatage(signalement, "declare_le", "constate_le")
    texte_long(signalement, "description")
    booleens(signalement, "jeu_essai")
    photo_en_lecture(signalement, "photo", RACINE_PHOTOS)
    masque(signalement, "id", "support_id", "uuid_terrain")
    # Ces valeurs par défaut existent aussi dans la base, mais sous une forme que les widgets ne savent pas
    # afficher (now(), false) : sans elles, le champ paraît vide et le bouton OK reste grisé à la création
    defaut(signalement, "nature", "'PANNE'")
    defaut(signalement, "statut", "'OUVERT'")
    defaut(signalement, "declare_le", "now()")
    defaut(signalement, "jeu_essai", "false")
    onglets(signalement, [("Signalement", ["point_id", "insee", "nature", "description"]),
                          ("Suivi", ["statut", "declare_le", "declarant", "jeu_essai", rel_suite]),
                          ("Terrain", ["constate_le", "photo"], '"uuid_terrain" IS NOT NULL')])
    signalement.setDisplayExpression("\"nature\" || ' du ' || format_date(\"declare_le\", 'dd/MM/yyyy')")
    lecture_seule(signalement, "point_id", "insee", "declare_le", "declarant", "jeu_essai", "constate_le", "photo")
    if not admin:
        lecture_seule(signalement, "statut")
    recherches(signalement, {"Ouverts depuis plus de 48 h": "\"statut\" = 'OUVERT' AND \"declare_le\" < now() - to_interval('2 days')",
                             "En cours": "\"statut\" IN ('OUVERT', 'PRIS_EN_COMPTE')",
                             "Danger pour le public": "\"nature\" = 'SECURITE' AND \"statut\" <> 'CLOS'"})
    if admin:
        action(signalement, QgsAction.GenericPython, "Créer l'intervention", ACTION_INTERVENTION)

    # Fiche d'intervention ---------------------------------------------------------------------
    alias(intervention, "intervention")
    liste(intervention, "insee", commune, "insee", "nom", nulle=False)
    liste(intervention, "entreprise_id", societe, "id", "nom")
    liste(intervention, "nature", ref["nature_intervention"], nulle=False)
    liste(intervention, "etat", ref["etat_intervention"], nulle=False)
    liste(intervention, "nouveau_type_source", ref["type_source"])
    reference(intervention, "point_id", rel_interventions, lecture=True)
    reference(intervention, "signalement_id", rel_suite, lecture=True)
    date(intervention, "date_prevue", "date_realisee")
    horodatage(intervention, "cree_le")
    texte_long(intervention, "compte_rendu")
    booleens(intervention, "jeu_essai")
    masque(intervention, "id", "support_id", "armoire_id")
    defaut(intervention, "etat", "'A_PLANIFIER'")
    defaut(intervention, "cree_le", "now()")
    defaut(intervention, "jeu_essai", "false")
    changement = "\"nature\" IN ('REMPLACEMENT_SOURCE', 'REMPLACEMENT_LUMINAIRE')"
    contrainte(intervention, "date_prevue", "\"etat\" <> 'PLANIFIEE' OR \"date_prevue\" IS NOT NULL", "Une intervention planifiée doit avoir une date prévue")
    contrainte(intervention, "date_realisee", "(\"etat\" <> 'REALISEE' OR \"date_realisee\" IS NOT NULL) AND (\"date_realisee\" IS NULL OR \"date_realisee\" <= now())",
               "Date de réalisation obligatoire une fois réalisée, jamais dans le futur")
    contrainte(intervention, "compte_rendu", "\"etat\" <> 'REALISEE' OR length(trim(\"compte_rendu\")) > 0", "Une intervention réalisée doit avoir un compte rendu")
    contrainte(intervention, "nouveau_type_source", f"\"etat\" <> 'REALISEE' OR NOT ({changement}) OR \"nouveau_type_source\" IS NOT NULL", "Préciser le nouveau type de source")
    contrainte(intervention, "nouvelle_puissance_w", f"\"etat\" <> 'REALISEE' OR NOT ({changement}) OR \"nouvelle_puissance_w\" > 0", "Préciser la nouvelle puissance")
    contrainte(intervention, "nouvelle_temperature", '"nouvelle_temperature" IS NULL OR "nouvelle_temperature" BETWEEN 1000 AND 10000', "Température comprise entre 1 000 et 10 000 K")
    onglets(intervention, [("Intervention", ["point_id", "signalement_id", "insee", "nature", "entreprise_id"]),
                           ("Réalisation", ["etat", "date_prevue", "date_realisee", "compte_rendu",
                                            ("Nouveau matériel", ["nouveau_type_source", "nouvelle_puissance_w", "nouvelle_temperature"], changement)]),
                           ("Suivi", ["cree_le", "cree_par", "jeu_essai"])])
    intervention.setDisplayExpression("\"nature\" || ' (' || \"etat\" || ')'")
    lecture_seule(intervention, "point_id", "signalement_id", "insee", "cree_le", "cree_par", "jeu_essai")
    if not admin:
        lecture_seule(intervention, "nature", "entreprise_id")
    recherches(intervention, {"En retard": "\"etat\" IN ('A_PLANIFIER', 'PLANIFIEE', 'EN_COURS') AND \"date_prevue\" < now()",
                              "À planifier": "\"etat\" = 'A_PLANIFIER'",
                              "En cours": "\"etat\" = 'EN_COURS'",
                              "Réalisées": "\"etat\" = 'REALISEE'"})

    # Fiche d'écart de contrôle ----------------------------------------------------------------
    if ecart:
        alias(ecart, "ecart")
        liste(ecart, "regle", regle, "code", "libelle", nulle=False)
        liste(ecart, "gestionnaire_id", gestionnaire, "id", "code")
        liste(ecart, "insee", commune, "insee", "nom")
        ecart.setEditorWidgetSetup(idx(ecart, "decision"), QgsEditorWidgetSetup("ValueMap", {"map": [
            {"À traiter": "a_traiter"}, {"Confirmée": "confirmee"}, {"Faux positif": "faux_positif"}, {"Corrigée": "corrigee"}]}))
        horodatage(ecart, "traite_le")
        texte_long(ecart, "commentaire")
        masque(ecart, "id")
        onglets(ecart, [("Écart", ["regle", "code_objet", "insee", "valeur_lue", "valeur_retenue", "mesure"]),
                        ("Décision", ["decision", "commentaire", "traite_par", "traite_le"])])
        ecart.setDisplayExpression("\"regle\" || ', ' || coalesce(\"code_objet\", '')")
        lecture_seule(ecart, "regle", "gestionnaire_id", "code_objet", "insee", "valeur_lue", "valeur_retenue", "mesure",
                      "table_objet", "objet_id", "traite_par", "traite_le")
        recherches(ecart, {"À traiter": "\"decision\" = 'a_traiter'",
                           "Positions": "left(\"regle\", 3) = 'POS'",
                           "Rapprochement entre les deux bases": "left(\"regle\", 3) = 'RAP'"})

    # Recherche et styles ----------------------------------------------------------------------
    for lyr in [armoire, support, point, signalement, intervention] + ([ecart] if ecart else []):
        non_cherchables(lyr)
    commune.setDisplayExpression('"nom"')
    for lyr in listes:
        lyr.setFlags(lyr.flags() & ~QgsMapLayer.Searchable & ~QgsMapLayer.Identifiable)
        lyr.setReadOnly(True)
    for lyr in [commune, fond]:
        lyr.setFlags(lyr.flags() & ~QgsMapLayer.Identifiable)

    regles(point, REGLES_SOURCE, taille=1.8)
    echelle_max(point, 100000)
    etiquettes(point, '"code"', 1500, taille=7)
    regles(support, [("Support", "TRUE", "#555555")], taille=1.1, forme="square")
    echelle_max(support, 5000)
    regles(armoire, [("Armoire", "NOT \"position_estimee\"", "#b2182b"),
                     ("Armoire, position estimée", "\"position_estimee\"", "#f4a582")], taille=3.0, forme="square", contour="#222222")
    echelle_max(armoire, 50000)
    etiquettes(armoire, '"code"', 10000, taille=8, couleur="#7a0c1d")
    regles(signalement, [("Ouvert", "\"statut\" = 'OUVERT'", "#d7301f"),
                         ("Pris en compte", "\"statut\" = 'PRIS_EN_COMPTE'", "#f28e2b"),
                         ("Clos", "\"statut\" = 'CLOS'", "#1a9850"),
                         ("Rejeté", "\"statut\" = 'REJETE'", "#9a9a9a")], taille=5.0, forme="triangle", contour="#222222")
    # Une intervention porte sur le même point que son signalement : le losange, plus petit, se dessine dans le triangle
    regles(intervention, [("À planifier", "\"etat\" = 'A_PLANIFIER'", "#d7301f"),
                          ("Planifiée", "\"etat\" = 'PLANIFIEE'", "#f28e2b"),
                          ("En cours", "\"etat\" = 'EN_COURS'", "#2b7bba"),
                          ("Réalisée", "\"etat\" = 'REALISEE'", "#1a9850"),
                          ("Annulée", "\"etat\" = 'ANNULEE'", "#9a9a9a")], taille=2.8, forme="diamond")
    if ecart:
        regles(ecart, [("Position", "left(\"regle\", 3) = 'POS'", "#d7301f"),
                       ("Rapprochement", "left(\"regle\", 3) = 'RAP'", "#7b5ea7"),
                       ("Cohérence", "left(\"regle\", 3) = 'COH'", "#f28e2b"),
                       ("Valeurs (à partir du 1:50 000)", "left(\"regle\", 3) = 'VAL'", "#c2a600", 50000),  # trop nombreuses en vue d'ensemble
                       ("Autres", "left(\"regle\", 3) NOT IN ('POS', 'RAP', 'COH', 'VAL')", "#555555")], taille=2.4, forme="cross2")
        echelle_max(ecart, 5000000)  # le thème de contrôle doit montrer quelque chose dès la vue d'ensemble
    contour = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#6b6b6b", "outline_width": "0.3", "outline_style": "dash"})
    commune.renderer().setSymbol(contour)
    etiquettes(commune, '"nom"', 150000, taille=9, couleur="#4a4a4a")

    # Arborescence et thèmes -------------------------------------------------------------------
    arbre = projet.layerTreeRoot()

    def groupe(nom, couches, replie=False):
        g = arbre.addGroup(nom)
        for lyr in couches:
            g.addLayer(lyr)
        g.setExpanded(not replie)
        return g

    groupe("Exploitation", [intervention, signalement])
    groupe("Patrimoine", [armoire, point, support])
    if ecart:
        groupe("Contrôle de la reprise", [ecart])
    groupe("Repères", [commune, fond])
    listes_groupe = groupe("Listes de valeurs", listes, replie=True)
    listes_groupe.setItemVisibilityChecked(False)

    modele = QgsLayerTreeModel(arbre)

    def theme(nom, visibles):
        for couche_arbre in arbre.findLayers():
            couche_arbre.setItemVisibilityChecked(couche_arbre.layer() in visibles)
        for g in arbre.findGroups():
            g.setItemVisibilityChecked(any(c.layer() in visibles for c in g.findLayers()))
        projet.mapThemeCollection().insert(nom, QgsMapThemeCollection.createThemeFromCurrentState(arbre, modele))

    if ecart:
        theme("Contrôle de la reprise", [ecart, commune, fond])
    theme("Pannes et interventions", [signalement, intervention, point, commune, fond])
    theme("Patrimoine", [armoire, point, support, commune, fond])  # dernier thème : état à l'ouverture

    # Vue de départ : la commune de démonstration, ou toute la métropole pour l'administrateur --
    filtre = "\"departement\" = '44'" if admin else f"\"insee\" = '{COMMUNE_DEMO}'"
    emprise = QgsRectangle()
    for entite in commune.getFeatures(filtre):
        emprise.combineExtentWith(entite.geometry().boundingBox())
    projet.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(emprise, crs))

    assert projet.write(), f"écriture du projet {profil} impossible"
    print(f"{profil} : {projet.fileName()}", flush=True)


if __name__ == "__main__":
    SORTIE.mkdir(exist_ok=True)
    app = QgsApplication([], True)
    app.initQgis()
    for nom_profil in PROFILS:
        construire(nom_profil)
    QgsProject.instance().clear()
    app.exitQgis()
