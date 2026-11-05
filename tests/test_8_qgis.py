"""T-APP : les projets QGIS, rouverts avec le compte de chaque profil (sans fenêtre).

T-IHM relit le parcours déroulé dans une vraie fenêtre QGIS par scripts/09_captures_qgis.py.
"""
import json
import subprocess

import pytest
from conftest import RACINE, valeur
import config

PROFILS = ["administrateur", "collectivite", "entreprise"]
ONGLETS = {"Points lumineux": ["Identification", "Matériel", "Photométrie", "Allumage", "Signalements", "Interventions", "Validité et origine"],
           "Interventions": ["Intervention", "Réalisation", "Suivi"], "Signalements": ["Signalement", "Suivi", "Terrain"]}


@pytest.fixture(scope="module")
def qgis(tmp_path_factory):
    sortie = tmp_path_factory.mktemp("qgis") / "resultats.json"
    subprocess.run([str(config.QGIS_PYTHON), "-u", str(RACINE / "tests" / "qgis_projets.py"), str(sortie)],
                   capture_output=True, text=True, errors="replace", timeout=400)
    return json.loads(sortie.read_text(encoding="utf-8"))


@pytest.mark.parametrize("profil", PROFILS)
def test_ouverture(qgis, constat, profil):
    """T-APP-01 : le projet s'ouvre, toutes ses couches sont valides, aucun mot de passe n'y est écrit"""
    r = qgis[profil]
    constat(f"{len(r['relations'])} relations, thèmes : {', '.join(r['themes'])}")
    assert r["lecture"] and not r["couches_invalides"] and r["sans_mot_de_passe"] and len(r["relations"]) == 5


@pytest.mark.parametrize("profil, communes", [("collectivite", ["44143"]), ("entreprise", ["44020", "44143"])])
def test_perimetre(qgis, su, constat, profil, communes):
    """T-APP-02 : dans QGIS, le profil ne voit que son périmètre"""
    r = qgis[profil]
    attendu = valeur(su, "SELECT count(*) FROM metier.point_lumineux WHERE insee = ANY(%s)", communes)
    constat(f"{r['points_vus']} points vus, communes {r['communes_vues']}")
    assert r["points_vus"] == attendu and r["communes_vues"] == communes


@pytest.mark.parametrize("profil, couche, droits", [
    ("administrateur", "Points lumineux", ["Ajouter", "Modifier", "Supprimer"]),
    ("collectivite", "Points lumineux", []),
    ("collectivite", "Signalements", ["Ajouter"]),
    ("collectivite", "Interventions", []),
    ("entreprise", "Points lumineux", []),
    ("entreprise", "Signalements", []),
    ("entreprise", "Interventions", ["Modifier"]),
])
def test_droits(qgis, constat, profil, couche, droits):
    """T-APP-03 : QGIS propose exactement les écritures permises par la base"""
    constat(f"{couche} : {qgis[profil]['droits'][couche] or 'lecture seule'}")
    assert qgis[profil]["droits"][couche] == droits


@pytest.mark.parametrize("couche", list(ONGLETS))
def test_onglets(qgis, constat, couche):
    """T-APP-04 : les fiches sont organisées en onglets, avec les fiches liées"""
    constat(", ".join(qgis["administrateur"]["onglets"][couche]))
    assert qgis["administrateur"]["onglets"][couche] == ONGLETS[couche]


@pytest.mark.parametrize("profil", PROFILS)
def test_recherches(qgis, constat, profil):
    """T-APP-05 : les recherches enregistrées s'exécutent toutes sur la base, sans erreur"""
    r = qgis[profil]
    constat(f"{len(r['recherches'])} recherches, {len(r['recherches_en_erreur'])} en erreur")
    assert len(r["recherches"]) >= 15 and not r["recherches_en_erreur"] and not r["affichage_invalide"]


def test_listes_hors_recherche(qgis, constat):
    """T-APP-06 : les listes de valeurs n'encombrent pas la barre de recherche"""
    n = qgis["administrateur"]["non_cherchables"]
    constat(f"{len(n)} couches exclues de la recherche")
    assert "Usage" in n and "Points lumineux" not in n and "Supports" not in n


@pytest.mark.parametrize("profil", PROFILS)
def test_photo_de_terrain(qgis, constat, profil):
    """T-APP-11 : la fiche d'un signalement retrouve le dossier des photos de terrain, depuis projets/ comme depuis projets/mon_postgres/"""
    r = qgis[profil]["photo_terrain"]
    constat(f"widget {r['widget']}, dossier {r['projets'].replace(RACINE.as_posix() + '/', '')}")
    attendu = (RACINE / "data" / "terrain" / "photos").as_posix()
    assert r["widget"] == "ExternalResource" and r["projets"] == attendu and r["mon_postgres"] == attendu


@pytest.mark.parametrize("contrainte, attendu", [
    ("realisee_sans_date_ni_compte_rendu", ["compte_rendu", "date_realisee"]),
    ("date_dans_le_futur", ["date_realisee"]),
    ("changement_sans_nouveau_materiel", ["nouveau_type_source", "nouvelle_puissance_w"]),
])
def test_contraintes_formulaire(qgis, constat, contrainte, attendu):
    """T-APP-07 : le formulaire d'intervention refuse les saisies incohérentes avant l'envoi à la base"""
    constat(f"champs signalés : {qgis['administrateur']['contraintes'][contrainte]}")
    assert qgis["administrateur"]["contraintes"][contrainte] == attendu


def test_signalement_par_qgis(qgis, constat):
    """T-APP-08 : à travers QGIS, la collectivité signale chez elle, jamais ailleurs, et la base signe la fiche"""
    r = qgis["collectivite"]
    constat(f"chez elle : {r['signaler_sur_son_perimetre']}, ailleurs : {r['signaler_hors_perimetre']}, déclarant {r['declarant_en_base']}, statut {r['statut_en_base']}")
    assert r["signaler_sur_son_perimetre"] is True and r["signaler_hors_perimetre"] is False
    assert r["signalement_ecrit_en_base"] == 1 and r["declarant_en_base"] == "demo_commune" and r["statut_en_base"] == "OUVERT"


def test_entreprise_par_qgis(qgis, constat):
    """T-APP-09 : à travers QGIS, l'entreprise ne peut ni changer la nature ni sauter d'étape"""
    r = qgis["entreprise"]
    constat(f"changer la nature : {r['changer_la_nature']}, sauter des états : {r['sauter_des_etats']}")
    assert r["changer_la_nature"] is False and r["sauter_des_etats"] is False


@pytest.fixture(scope="module")
def ihm():
    return json.loads((RACINE / "livrables" / "recette" / "ihm.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("profil", PROFILS)
def test_parcours_fenetre(ihm, constat, profil):
    """T-IHM-01 : chaque profil ouvre son projet dans une vraie fenêtre QGIS et son parcours aboutit"""
    r = ihm[profil]
    constat(", ".join(f"{k} : {'ok' if v == 'ok' else 'erreur'}" for k, v in r["etapes"].items()))
    assert r["projet_ouvert"] and not r["couches_invalides"] and all(v == "ok" for v in r["etapes"].values())


def test_action_signaler(ihm, constat):
    """T-IHM-02 : l'action « Signaler une panne » ouvre la fiche, le bouton OK enregistre, la base complète la fiche"""
    r = ihm["collectivite"]
    constat(f"fiche ouverte : {r.get('fiche_ouverte')}, OK actif : {r.get('ok_actif')}, en base : {r.get('signalement_en_base')}")
    assert r["fiche_ouverte"] and r["ok_actif"] and "fiche_restee_ouverte" not in r
    declarant, statut, insee, point = r["signalement_en_base"]
    assert declarant == "demo_commune" and statut == "OUVERT" and insee == "44143" and point == r["point_attendu"]


def test_modele_graphique(constat):
    """T-APP-10 : le modèle graphique de QGIS et la reprise SQL donnent le même résultat, objet par objet"""
    r = json.loads((RACINE / "livrables" / "recette" / "croisement_modele.json").read_text(encoding="utf-8"))
    constat(f"{r['objets_compares']} objets comparés, valeurs renseignées {r['valeurs_renseignees']}, différences {r['differences']}, "
            f"écart de position maximal {r['ecart_position_max_m']} m")
    assert r["objets_compares"] > 97000 and r["absents_de_la_base"] == 0
    assert all(n > 50000 for n in r["valeurs_renseignees"].values())
    assert not any(r["differences"].values()) and r["ecart_position_max_m"] < 0.001


@pytest.mark.parametrize("nom", ["fiche_point_materiel", "fiche_support", "fiche_signalement_saisie", "fiche_intervention_realisation", "fiche_ecart",
                                 "qgis_administrateur_controle", "qgis_collectivite_patrimoine", "qgis_entreprise_interventions"])
def test_captures(constat, nom):
    """T-IHM-03 : les captures des supports de formation sont produites"""
    fichier = RACINE / "docs" / "captures" / f"{nom}.png"
    constat(f"{fichier.stat().st_size // 1024} Ko")
    assert fichier.stat().st_size > 5000
