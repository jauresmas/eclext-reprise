"""T-TER : du paquet QField jusqu'à la base.

Le téléphone est simulé par tests/qgis_terrain.py, qui utilise le moteur de QGIS sur lequel QField s'appuie. L'essai sur un
vrai téléphone reste à faire : c'est la vérification T-MAN-06 du cahier de recette.
"""
import csv
import importlib
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid
import zipfile

import pytest
from conftest import RACINE, connecter, lignes, valeur
import config

PAQUET = RACINE / "projets" / "qfield" / "eclairage_terrain_demo_commune.zip"
FONCTION = "SELECT * FROM exploitation.importer_signalements_terrain(%s::jsonb)"


def appeler(conn, *rangees):
    return lignes(conn, FONCTION, json.dumps(rangees))


@pytest.fixture(scope="module")
def telephone(tmp_path_factory):
    """Le paquet ouvert et rempli dans un dossier au nom accentué, loin du dossier d'origine."""
    racine = tmp_path_factory.mktemp("terrain")
    travail = racine / "téléphone" / "Imported Projects" / "eclairage terrain"
    sortie = racine / "resultats.json"
    subprocess.run([str(config.QGIS_PYTHON), "-u", str(RACINE / "tests" / "qgis_terrain.py"), str(PAQUET), str(travail), str(sortie)],
                   capture_output=True, text=True, errors="replace", timeout=300)
    return {"r": json.loads(sortie.read_text(encoding="utf-8")), "dossier": travail}


@pytest.fixture
def point_chez_elle():
    conn = connecter("demo_commune")
    yield valeur(conn, "SELECT min(id) FROM metier.point_lumineux WHERE retire_le IS NULL")
    conn.close()


@pytest.fixture
def point_ailleurs(su):
    return valeur(su, "SELECT min(id) FROM metier.point_lumineux WHERE insee = '44215'")


@pytest.fixture
def nettoyer_base():
    """L'import en ligne de commande valide ses lignes : on les efface à la fin, avec leur trace au journal."""
    a_effacer = []
    yield a_effacer
    conn = connecter()
    with conn, conn.cursor() as cur:
        for u in a_effacer:
            cur.execute("DELETE FROM exploitation.signalement WHERE uuid_terrain = %s", (u,))  # d'abord : cet effacement s'inscrit lui aussi au journal
            cur.execute("DELETE FROM audit.journal WHERE table_nom = 'exploitation.signalement' AND (apres ->> 'uuid_terrain' = %s OR avant ->> 'uuid_terrain' = %s)", (u, u))
    conn.close()


def test_paquet_autonome(telephone, constat):
    """T-TER-01 : le paquet s'ouvre hors de son dossier d'origine, sans connexion à la base ni mot de passe"""
    r = telephone["r"]
    constat(f"couches : {', '.join(r['couches'])} ; fichiers : {', '.join(r['fichiers'])}")
    assert r["lecture"] and not r["invalides"] and not r["sources_hors_paquet"] and not r["traces_de_base"]
    assert "postgres" not in r["fournisseurs"].values()
    assert PAQUET.stat().st_size < 5_000_000


def test_paquet_perimetre(telephone, su, constat):
    """T-TER-02 : le paquet ne contient que le périmètre du compte, extrait avec ce compte"""
    r = telephone["r"]
    attendu = valeur(su, "SELECT count(*) FROM metier.point_lumineux WHERE insee = '44143' AND retire_le IS NULL")
    total = valeur(su, "SELECT count(*) FROM metier.point_lumineux")
    constat(f"{r['points']} points sur {total}, communes {r['communes']}")
    assert r["points"] == attendu and r["communes"] == ["44143"]


def test_paquet_saisie_seule(telephone, constat):
    """T-TER-03 : sur le téléphone, seule la couche de saisie est modifiable, et elle part vide"""
    r = telephone["r"]
    constat(f"modifiable : {r['modifiables']}, lignes au départ : {r['saisies_au_depart']}")
    assert r["modifiables"] == ["Signaler une panne"] and r["saisies_au_depart"] == 0


def test_fiche_preremplie(telephone, constat):
    """T-TER-04 : le repère posé à 3 m d'un point ouvre une fiche remplie sur ce point"""
    r = telephone["r"]
    constat(f"{r['propose']['code_point']}, {r['propose']['voie']}, {r['propose']['distance_m']} m, fiche ouverte en {r['duree_fiche_s']} s")
    assert r["propose"]["point_id"] == r["attendu"]["id"] and r["propose"]["code_point"] == r["attendu"]["code"]
    assert r["propose"]["voie"] == r["attendu"]["voie"] and r["propose"]["distance_m"] == 3 and r["propose"]["nature"] == "PANNE"
    assert uuid.UUID(r["uuid"]) and r["constate_ms"] > 1_700_000_000_000 and not r["erreurs_fiche_correcte"]


def test_fiche_refus(telephone, constat):
    """T-TER-05 : la fiche refuse un repère loin de tout point, et « Autre » sans description"""
    r = telephone["r"]
    constat(f"loin de tout point : {r['loin_erreurs']} ; Autre sans description : {r['autre_sans_description']}")
    assert r["loin_code"] is None and "code_point" in r["loin_erreurs"]
    assert "description" in r["autre_sans_description"] and not r["autre_avec_description"]


def test_fiche_photo(telephone, constat):
    """T-TER-06 : la photo passe par le widget de pièce jointe, avec un chemin relatif au projet, et le repère s'accroche aux points"""
    r = telephone["r"]
    constat(f"widget {r['widget_photo']}, stockage relatif {r['stockage_photo']}, accroche {r['accroche']}")
    assert r["widget_photo"] == "ExternalResource" and r["stockage_photo"] == 1 and r["accroche"]
    assert r["champs_fiche"] == ["code_point", "voie", "distance_m", "nature", "description", "photo"]
    assert r["photo_ecrite"] and r["enregistre"] and r["saisies_a_la_fin"] == 2


def test_import_ligne(compte, su, point_chez_elle, constat):
    """T-TER-07 : une ligne importée est signée par la base, placée sur son point, et une seconde passe ne crée pas de doublon"""
    conn = compte("demo_commune")
    u = str(uuid.uuid4())
    ligne = {"uuid_terrain": u, "point_id": point_chez_elle, "nature": "PANNE", "description": "Essai", "constate_ms": 1_700_000_000_000, "photo": f"{u}.jpg"}
    premiere = appeler(conn, ligne)
    seconde = appeler(conn, ligne)
    declarant, statut, insee, meme_position, constate, photo = lignes(conn, """
        SELECT s.declarant, s.statut, s.insee, ST_Equals(s.geom, p.geom), s.constate_le = to_timestamp(1700000000), s.photo
        FROM exploitation.signalement s JOIN metier.point_lumineux p ON p.id = s.point_id WHERE s.uuid_terrain = %s""", u)[0]
    constat(f"{premiere[0][1]} puis {seconde[0][1]}, signé {declarant}, statut {statut}, commune {insee}")
    assert premiere[0][1] == "importee" and seconde[0][1] == "deja_importee"
    assert declarant == "demo_commune" and statut == "OUVERT" and insee == "44143" and meme_position and constate and photo == f"{u}.jpg"
    assert valeur(conn, "SELECT count(*) FROM exploitation.signalement WHERE uuid_terrain = %s", u) == 1


def test_import_refus(compte, point_chez_elle, point_ailleurs, constat):
    """T-TER-08 : chaque ligne fautive est refusée avec son motif, sans bloquer les autres"""
    conn = compte("demo_commune")
    bonne = {"uuid_terrain": str(uuid.uuid4()), "point_id": point_chez_elle, "nature": "PANNE"}
    fautives = {
        "hors périmètre": {"uuid_terrain": str(uuid.uuid4()), "point_id": point_ailleurs, "nature": "PANNE"},
        "point inconnu": {"uuid_terrain": str(uuid.uuid4()), "point_id": 999999999, "nature": "PANNE"},
        "sans point": {"uuid_terrain": str(uuid.uuid4()), "point_id": None, "nature": "PANNE"},
        "nature inconnue": {"uuid_terrain": str(uuid.uuid4()), "point_id": point_chez_elle, "nature": "INVENTEE"},
        "sans identifiant": {"uuid_terrain": None, "point_id": point_chez_elle, "nature": "PANNE"},
        "identifiant faux": {"uuid_terrain": "pas-un-identifiant", "point_id": point_chez_elle, "nature": "PANNE"},
        "date future": {"uuid_terrain": str(uuid.uuid4()), "point_id": point_chez_elle, "nature": "PANNE", "constate_ms": 4_102_444_800_000},
        "photo avec dossier": {"uuid_terrain": str(uuid.uuid4()), "point_id": point_chez_elle, "nature": "PANNE", "photo": "../../secret.jpg"},
    }
    reponses = appeler(conn, *fautives.values(), bonne)
    constat(" ; ".join(f"{nom} : {r[2]}" for nom, r in zip(fautives, reponses))[:600])
    assert [r[1] for r in reponses] == ["refusee"] * len(fautives) + ["importee"]
    assert all(r[2] for r in reponses[:-1]) and reponses[0][2] == "Point hors du périmètre de ce compte"


@pytest.mark.parametrize("login, permis", [("demo_commune", True), ("demo_admin", True), ("demo_entreprise", False), ("demo_lecture", False)])
def test_import_droits(su, login, permis, constat):
    """T-TER-09 : seuls la collectivité et l'administrateur peuvent verser des pannes"""
    droit = valeur(su, "SELECT has_function_privilege(%s, 'exploitation.importer_signalements_terrain(jsonb)', 'EXECUTE')", login)
    constat(f"droit d'exécution : {droit}")
    assert droit is permis


def test_import_complet(telephone, su, point_ailleurs, tmp_path, nettoyer_base, constat):
    """T-TER-10 : le dossier du téléphone arrive dans la base : bilan juste, photo copiée, refus expliqué, second import sans doublon"""
    dossier = tmp_path / "retour"
    shutil.copytree(telephone["dossier"], dossier)
    fautif = str(uuid.uuid4())
    base = sqlite3.connect(dossier / "signalements_terrain.gpkg")
    # Une ligne falsifiée, que la fiche n'aurait pas laissé passer. Les déclencheurs d'index spatial de GeoPackage exigent des fonctions absentes de sqlite3
    for nom, in base.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
        base.execute(f'DROP TRIGGER "{nom}"')
    base.execute("INSERT INTO signalements_terrain (uuid_terrain, point_id, code_point, nature) VALUES (?, ?, 'AILLEURS', 'PANNE')", (fautif, point_ailleurs))
    base.commit()
    uuids = [u for u, in base.execute("SELECT uuid_terrain FROM signalements_terrain")]
    base.close()
    nettoyer_base.extend(uuids)

    archive = tmp_path / "retour.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for f in dossier.rglob("*"):
            z.write(f, f.relative_to(dossier))
    photos, rapports = tmp_path / "photos", tmp_path / "rapports"
    commande = [sys.executable, str(RACINE / "scripts" / "13_importer_terrain.py"), str(archive), "--port", str(config.PG_PORT), "--photos", str(photos), "--rapports", str(rapports)]
    premiere = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert premiere.returncode == 0, premiere.stdout + premiere.stderr
    constat(premiere.stdout.splitlines()[0])
    assert "Reçues 3 : importées 2, déjà importées 0, refusées 1." in premiere.stdout

    rangees = {r["point_lumineux"]: r for r in csv.DictReader(next(rapports.glob("*.csv")).open(encoding="utf-8-sig"), delimiter=";")}
    assert rangees["AILLEURS"]["resultat"] == "refusee" and "périmètre" in rangees["AILLEURS"]["motif"]
    avec_photo = lignes(su, "SELECT photo, description, declarant FROM exploitation.signalement WHERE uuid_terrain = ANY(%s::uuid[]) AND photo IS NOT NULL", uuids)
    assert len(avec_photo) == 1 and avec_photo[0][1] == "Éteint depuis l'orage d'hier" and avec_photo[0][2] == "demo_commune"
    assert (photos / avec_photo[0][0]).stat().st_size > 0 and len(list(photos.iterdir())) == 1

    su.rollback()
    seconde = subprocess.run(commande, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert "Reçues 3 : importées 0, déjà importées 2, refusées 1." in seconde.stdout, seconde.stdout + seconde.stderr
    assert valeur(su, "SELECT count(*) FROM exploitation.signalement WHERE uuid_terrain = ANY(%s::uuid[])", uuids) == 2


def test_import_journal_wal(telephone, tmp_path, nettoyer_base, constat):
    """T-TER-11 : une panne encore dans le fichier -wal de SQLite, projet resté ouvert dans QField, n'est pas perdue"""
    dossier = tmp_path / "ouvert"
    shutil.copytree(telephone["dossier"], dossier)
    u = str(uuid.uuid4())
    nettoyer_base.append(u)
    gpkg = dossier / "signalements_terrain.gpkg"
    ouvert = sqlite3.connect(gpkg)
    for nom, in ouvert.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
        ouvert.execute(f'DROP TRIGGER "{nom}"')
    ouvert.commit()
    ouvert.execute("PRAGMA journal_mode = WAL")
    ouvert.execute("PRAGMA wal_autocheckpoint = 0")
    point = valeur(connecter("demo_commune"), "SELECT min(id) FROM metier.point_lumineux")
    ouvert.execute("DELETE FROM signalements_terrain")
    ouvert.execute("INSERT INTO signalements_terrain (uuid_terrain, point_id, code_point, nature) VALUES (?, ?, 'WAL', 'PANNE')", (u, point))
    ouvert.commit()
    copie = tmp_path / "copie"
    copie.mkdir()
    for nom in ("signalements_terrain.gpkg", "signalements_terrain.gpkg-wal"):  # le -shm reste verrouillé, et SQLite sait s'en passer
        shutil.copy(dossier / nom, copie / nom)
    ouvert.close()
    assert (copie / "signalements_terrain.gpkg-wal").stat().st_size > 0

    r = subprocess.run([sys.executable, str(RACINE / "scripts" / "13_importer_terrain.py"), str(copie), "--port", str(config.PG_PORT),
                        "--photos", str(tmp_path / "p"), "--rapports", str(tmp_path / "r")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    constat(r.stdout.splitlines()[0] if r.stdout else r.stderr)
    assert "Reçues 1 : importées 1" in r.stdout, r.stdout + r.stderr


def test_import_photo_hors_dossier(tmp_path, constat):
    """T-TER-12 : un chemin de photo venu du téléphone ne peut pas faire lire un fichier hors de l'envoi"""
    sys.path.insert(0, str(RACINE / "scripts"))
    module = importlib.import_module("13_importer_terrain")
    dehors = tmp_path / "secret.jpg"
    dehors.write_bytes(b"x")
    racine = tmp_path / "envoi"
    (racine / "DCIM").mkdir(parents=True)
    (racine / "DCIM" / "a.jpg").write_bytes(b"x")
    (racine / "DCIM" / "script.bat").write_bytes(b"x")
    constat("chemin relatif, chemin absolu, remontée et extension interdite testés")
    assert module.trouver_photo(racine, "DCIM/a.jpg") == (racine / "DCIM" / "a.jpg").resolve()
    assert module.trouver_photo(racine, "../secret.jpg") is None and module.trouver_photo(racine, str(dehors)) is None
    assert module.trouver_photo(racine, "DCIM/script.bat") is None and module.trouver_photo(racine, None) is None
