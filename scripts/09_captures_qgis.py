"""Étape 9 : déroule le parcours de chaque profil dans un QGIS déjà ouvert, et le capture.

C'est aussi un test : les projets s'ouvrent comme pour un utilisateur, et la fiche « Signaler une panne » est
réellement remplie puis validée avec le bouton OK. Résultats dans livrables/recette/ihm.json, captures dans
docs/captures/ ; le signalement d'essai est effacé. Toute fenêtre ouverte est refermée, même en cas d'erreur,
et le script laisse un projet vide à la fin. À lancer dans la console Python de QGIS, projet vide :

    chemin = r"...\\scripts\\09_captures_qgis.py"
    exec(open(chemin, encoding="utf-8").read(), {"__file__": chemin})
"""
import json
import traceback
from pathlib import Path

import psycopg2
from qgis.core import QgsExpressionContext, QgsExpressionContextUtils, QgsProject, QgsRectangle
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QPainter, QPixmap
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QPlainTextEdit, QTabWidget
from qgis.utils import iface

RACINE = Path(__file__).resolve().parents[1]
CAPTURES = RACINE / "docs" / "captures"
RESULTAT = RACINE / "livrables" / "recette" / "ihm.json"
MARQUE = "Essai automatique de la recette, à effacer"
resultats = {}
etapes = []


def couche(nom):
    return QgsProject.instance().mapLayersByName(nom)[0]


def base():
    return psycopg2.connect(host="localhost", port=5436, dbname="eclext", user="postgres")


def ecrire():
    RESULTAT.write_text(json.dumps(resultats, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def replier(noeud):
    """Seul ce que la carte affiche garde sa légende ouverte : le reste la pousserait hors de la capture."""
    for enfant in noeud.children():
        enfant.setExpanded(enfant.isVisible())
        replier(enfant)


def theme(nom, rue=False):
    if rue:
        centre = next(couche("Signalements").getFeatures()).geometry().asPoint()
        iface.mapCanvas().setExtent(QgsRectangle(centre.x() - 300, centre.y() - 170, centre.x() + 300, centre.y() + 170))
    racine = QgsProject.instance().layerTreeRoot()
    QgsProject.instance().mapThemeCollection().applyTheme(nom, racine, iface.layerTreeView().layerTreeModel())
    replier(racine)
    iface.mapCanvas().refresh()


def fenetre(nom):
    """Liste des couches et carte côte à côte : pas les barres d'outils ni les panneaux propres à ce poste."""
    arbre, carte = iface.layerTreeView().grab(), iface.mapCanvas().grab()
    # En pixels réels : sur un écran à 125 %, grab() annonce une taille réduite et l'image gardait une marge blanche
    arbre.setDevicePixelRatio(1)
    carte.setDevicePixelRatio(1)
    image = QPixmap(arbre.width() + carte.width(), carte.height())
    image.fill(iface.layerTreeView().palette().base().color())
    peintre = QPainter(image)
    peintre.drawPixmap(0, 0, arbre)
    peintre.drawPixmap(arbre.width(), 0, carte)
    peintre.end()
    image.save(str(CAPTURES / nom))


def fiche(nom_couche, filtre, onglet, fichier, largeur=660, hauteur=540):
    dialogue = iface.getFeatureForm(couche(nom_couche), next(couche(nom_couche).getFeatures(filtre)))
    try:
        dialogue.setFixedSize(largeur, hauteur)
        dialogue.show()
        dialogue.findChildren(QTabWidget)[0].setCurrentIndex(onglet)
        QApplication.processEvents()
        dialogue.grab().save(str(CAPTURES / fichier))
    finally:
        dialogue.reject()
        dialogue.deleteLater()


def signaler(profil):
    """L'action de la couche ouvre la fiche ; on écrit la description et on clique sur OK."""
    points = couche("Points lumineux")
    entite = next(points.getFeatures("\"type_source\" = 'LED'"))
    identifiant = next(a.id() for a in points.actions().actions() if a.name() == "Signaler une panne")
    contexte = QgsExpressionContext()
    contexte.appendScope(QgsExpressionContextUtils.layerScope(points))
    trace = resultats[profil]

    def remplir():
        dialogue = QApplication.activeModalWidget()
        trace["fiche_ouverte"] = dialogue is not None and dialogue.metaObject().className() == "QgsAttributeDialog"
        if dialogue is None:
            return
        try:
            dialogue.setFixedSize(660, 460)
            dialogue.findChild(QPlainTextEdit).setPlainText(MARQUE)
            QApplication.processEvents()
            dialogue.grab().save(str(CAPTURES / "fiche_signalement_saisie.png"))
            bouton = dialogue.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
            trace["ok_actif"] = bouton.isEnabled()
            bouton.click()
        except Exception:
            trace["erreur_fiche"] = traceback.format_exc()
        QTimer.singleShot(1500, fermer_si_ouvert)

    def fermer_si_ouvert():
        reste = QApplication.activeModalWidget()
        if reste is not None:
            trace["fiche_restee_ouverte"] = reste.windowTitle()
            reste.reject()

    QTimer.singleShot(2000, remplir)
    points.actions().doAction(identifiant, entite, contexte)
    with base() as c, c.cursor() as cur:
        cur.execute("SELECT declarant, statut, insee, point_id FROM exploitation.signalement WHERE description = %s", (MARQUE,))
        trace["signalement_en_base"] = cur.fetchone()
        trace["point_attendu"] = entite["id"]
        cur.execute("DELETE FROM exploitation.signalement WHERE description = %s", (MARQUE,))
        cur.execute("DELETE FROM audit.journal WHERE avant ->> 'description' = %s OR apres ->> 'description' = %s", (MARQUE, MARQUE))


def ouvrir(profil):
    QgsProject.instance().setDirty(False)
    chemin = RACINE / "projets" / f"eclairage_{profil}.qgz"
    resultats[profil] = {"projet_ouvert": iface.addProject(str(chemin)),
                         "couches_invalides": [c.name() for c in QgsProject.instance().mapLayers().values() if not c.isValid()],
                         "etapes": {}}


def etape(profil, nom, fonction, delai=800):
    def lancer():
        try:
            fonction()
            resultats[profil]["etapes"][nom] = "ok"
        except Exception:
            resultats[profil]["etapes"][nom] = traceback.format_exc()
    etapes.append((delai, lancer))


def parcours():
    p = "administrateur"
    etapes.append((500, lambda: ouvrir(p)))
    etape(p, "theme", lambda: theme("Contrôle de la reprise"), 4000)
    etape(p, "fenetre", lambda: fenetre("qgis_administrateur_controle.png"), 15000)
    etape(p, "fiche_support", lambda: fiche("Supports", "\"hauteur_m\" IS NOT NULL AND \"type_massif\" IS NOT NULL", 1, "fiche_support.png"))
    etape(p, "fiche_ecart", lambda: fiche("Écarts de contrôle", "\"regle\" = 'POS_05'", 0, "fiche_ecart.png", hauteur=400))

    q = "collectivite"
    etapes.append((800, lambda: ouvrir(q)))
    etape(q, "theme", lambda: theme("Patrimoine", rue=True), 4000)
    etape(q, "fenetre", lambda: fenetre("qgis_collectivite_patrimoine.png"), 15000)
    etape(q, "fiche_point", lambda: fiche("Points lumineux", "\"type_source\" = 'LED' AND \"puissance_w\" IS NOT NULL", 1, "fiche_point_materiel.png"))
    etape(q, "signaler", lambda: signaler(q))

    e = "entreprise"
    etapes.append((800, lambda: ouvrir(e)))
    etape(e, "theme", lambda: theme("Pannes et interventions", rue=True), 4000)
    etape(e, "fenetre", lambda: fenetre("qgis_entreprise_interventions.png"), 15000)
    etape(e, "fiche_intervention", lambda: fiche("Interventions", "\"etat\" = 'REALISEE'", 1, "fiche_intervention_realisation.png"))


def suivant():
    ecrire()
    if not etapes:
        QgsProject.instance().setDirty(False)
        iface.newProject(False)
        resultats["termine"] = True
        ecrire()
        return
    delai, fonction = etapes.pop(0)

    def lancer():
        try:
            fonction()
        finally:
            suivant()
    QTimer.singleShot(delai, lancer)


CAPTURES.mkdir(parents=True, exist_ok=True)
RESULTAT.parent.mkdir(parents=True, exist_ok=True)
parcours()
suivant()
