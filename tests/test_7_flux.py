"""T-FLX : prise en compte d'une nouvelle publication, sur une copie de la base.

On fabrique un nouveau lot à partir du vrai fichier de Nantes Métropole : 5 foyers retirés, 4 puissances
modifiées, 2 foyers ajoutés. Le chargement, la reprise et les contrôles tournent avec les vrais scripts,
sur la copie, qui est supprimée à la fin. Aucun projet QGIS ne doit être ouvert : la copie exige une base sans connexion.
"""
import collections
import csv
import hashlib
import json
import os
import subprocess
import sys

import pytest
from conftest import RACINE, connecter, executer, lignes, valeur

COPIE = "eclext_essai"
FOYER, SUPPORT, PUISSANCE, COMMUNE = "Identifiant du  foyer", "Identifiant du support", "Puissance du foyer (W)", "Nom de la commune"


def lancer(script, *arguments):
    env = dict(os.environ, ECLEXT_BASE=COPIE, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, script, *arguments], cwd=RACINE / "scripts", env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    return r.stdout + r.stderr


def empreinte(conn):
    """Numéros de transaction de toutes les lignes : si rien n'est réécrit, ils ne bougent pas."""
    return lignes(conn, """SELECT (SELECT sum(xmin::text::bigint) FROM metier.point_lumineux),
                                  (SELECT sum(xmin::text::bigint) FROM metier.support),
                                  (SELECT sum(xmin::text::bigint) FROM metier.armoire)""")[0]


def fabriquer_lot(dossier):
    """Le lot suivant : ne change que les lignes annoncées, le reste du fichier est recopié."""
    origine = max(d for d in (RACINE / "data" / "sources" / "nantes").iterdir() if (d / "manifeste.json").exists())
    manifeste = json.loads((origine / "manifeste.json").read_text(encoding="utf-8"))
    with open(origine / manifeste["fichier"], encoding="utf-8-sig", newline="") as f:
        lecteur = csv.DictReader(f, delimiter=";")
        entete, foyers = lecteur.fieldnames, list(lecteur)

    par_foyer = collections.Counter(l[FOYER] for l in foyers)
    par_support = collections.Counter(l[SUPPORT] for l in foyers)
    simples = [l for l in foyers if l[COMMUNE] == "NANTES" and par_foyer[l[FOYER]] == 1 and par_support[l[SUPPORT]] == 1
               and l[PUISSANCE] not in ("", "77")]
    retires, modifies, modeles = simples[100:105], simples[200:204], simples[300:302]
    codes_retires = {l[FOYER] for l in retires}
    for ligne in modifies:
        ligne[PUISSANCE] = "77"
    ajouts = [dict(m, **{FOYER: f"ESSAI{i:06d}", SUPPORT: f"ESSAI{i:06d}"}) for i, m in enumerate(modeles, start=1)]

    dossier.mkdir()
    with open(dossier / manifeste["fichier"], "w", encoding="utf-8", newline="") as f:
        ecrivain = csv.DictWriter(f, fieldnames=entete, delimiter=";", lineterminator="\n")
        ecrivain.writeheader()
        ecrivain.writerows(l for l in foyers if l[FOYER] not in codes_retires)
        ecrivain.writerows(ajouts)
    contenu = (dossier / manifeste["fichier"]).read_bytes()
    manifeste.update(date_collecte="20261201", sha256=hashlib.sha256(contenu).hexdigest(), taille=len(contenu))
    (dossier / "manifeste.json").write_text(json.dumps(manifeste), encoding="utf-8")
    return ([l[FOYER] for l in retires], [l[FOYER] for l in modifies], [l[FOYER] for l in ajouts],
            [l[SUPPORT] for l in retires], [l[SUPPORT] for l in ajouts])


@pytest.fixture(scope="module")
def flux(tmp_path_factory):
    admin = connecter(base="postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {COPIE} WITH (FORCE)")
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'eclext' AND pid <> pg_backend_pid()")
        cur.execute(f"CREATE DATABASE {COPIE} TEMPLATE eclext")
    conn = connecter(base=COPIE)
    conn.autocommit = True
    try:
        dossier = tmp_path_factory.mktemp("lot") / "20261201"
        retires, modifies, ajouts, supports_retires, supports_ajoutes = fabriquer_lot(dossier)

        # Trois corrections faites sur place, sans toucher à maj_locale : la publication ne doit pas les écraser.
        # Le premier foyer modifié change aussi dans la source, à 77 W.
        local = modifies[0]
        executer(conn, "UPDATE metier.point_lumineux SET puissance_w = 999 WHERE code = %s", local)
        support_local = valeur(conn, "SELECT min(code) FROM metier.support WHERE insee = '44020' AND hauteur_m IS NOT NULL")
        executer(conn, "UPDATE metier.support SET hauteur_m = 12.5 WHERE code = %s", support_local)
        armoire_locale = valeur(conn, "SELECT min(code) FROM metier.armoire WHERE insee = '44020'")
        position = valeur(conn, "UPDATE metier.armoire SET geom = ST_Translate(geom, 10, 0), position_estimee = false WHERE code = %s RETURNING ST_AsText(geom)", armoire_locale)

        charge = lancer("02_charger_sources.py", "--source", "nantes", "--dossier", str(dossier))
        lancer("03_reprise.py")
        premiere = empreinte(conn)
        lancer("03_reprise.py")
        seconde = empreinte(conn)
        rechargement = lancer("02_charger_sources.py", "--source", "nantes", "--dossier", str(dossier))
        lancer("04_controles.py")
        yield {"conn": conn, "retires": retires, "modifies": modifies[1:], "local": local, "support_local": support_local,
               "armoire_locale": armoire_locale, "position": position, "ajouts": ajouts,
               "supports_retires": supports_retires, "supports_ajoutes": supports_ajoutes,
               "premiere": premiere, "seconde": seconde, "charge": charge, "rechargement": rechargement}
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {COPIE} WITH (FORCE)")
        admin.close()


def test_lot_enregistre(flux, constat):
    """T-FLX-01 : le nouveau lot devient le lot courant, l'ancien reste en base"""
    lots = lignes(flux["conn"], "SELECT date_collecte, courant, nb_lignes FROM flux.lot WHERE source = 'nantes' ORDER BY id")
    constat(", ".join(f"{d} ({n} lignes{', courant' if c else ''})" for d, c, n in lots))
    assert len(lots) == 2 and lots[1][1] and not lots[0][1] and lots[1][2] == lots[0][2] - 5 + 2


def test_differentiel(flux, constat):
    """T-FLX-02 : le différentiel entre les deux lots annonce exactement ce qui a changé"""
    natures = dict(lignes(flux["conn"], "SELECT nature, count(*) FROM flux.ecart_lot WHERE source = 'nantes' GROUP BY 1"))
    champs = lignes(flux["conn"], "SELECT DISTINCT unnest(champs) FROM flux.ecart_lot WHERE source = 'nantes' AND nature = 'modification'")
    constat(f"{natures}, champ modifié : {[c[0] for c in champs]}")
    assert natures == {"retrait": 5, "modification": 4, "ajout": 2} and champs == [("puissance_du_foyer_w",)]


def test_retires(flux, constat):
    """T-FLX-03 : un point absent du nouveau lot est retiré et daté, jamais supprimé, et sort de l'export"""
    r = lignes(flux["conn"], "SELECT code, retire_le FROM metier.point_lumineux WHERE code = ANY(%s)", flux["retires"])
    s = valeur(flux["conn"], "SELECT count(*) FROM metier.support WHERE code = ANY(%s) AND retire_le IS NOT NULL", flux["supports_retires"])
    constat(f"{len(r)} points gardés, retirés le {sorted({str(x[1]) for x in r})}, {s} supports retirés")
    assert len(r) == 5 and all(str(x[1]) == "2026-12-01" for x in r) and s == 5
    assert valeur(flux["conn"], "SELECT count(*) FROM eclext.pointlumineux WHERE identifiant = ANY(%s)", flux["retires"]) == 0


def test_modifies(flux, constat):
    """T-FLX-04 : une valeur changée dans la source est mise à jour"""
    valeurs = {x[0] for x in lignes(flux["conn"], "SELECT puissance_w FROM metier.point_lumineux WHERE code = ANY(%s)", flux["modifies"])}
    constat(f"puissances relues : {sorted(float(v) for v in valeurs)}")
    assert valeurs == {77}


def test_ajouts(flux, constat):
    """T-FLX-05 : un nouveau foyer de la source est créé, avec son support, et part à l'export"""
    n = valeur(flux["conn"], "SELECT count(*) FROM eclext.pointlumineux WHERE identifiant = ANY(%s)", flux["ajouts"])
    m = valeur(flux["conn"], "SELECT count(*) FROM metier.support WHERE code = ANY(%s) AND retire_le IS NULL", flux["supports_ajoutes"])
    constat(f"{n} points à l'export, {m} supports créés")
    assert n == 2 and m == 2


def test_modification_locale_protegee(flux, constat):
    """T-FLX-06 : un point, un support et une armoire corrigés après la reprise ne sont pas écrasés par la nouvelle publication"""
    conn = flux["conn"]
    puissance, drapeau_point = lignes(conn, "SELECT puissance_w, maj_locale FROM metier.point_lumineux WHERE code = %s", flux["local"])[0]
    hauteur, drapeau_support = lignes(conn, "SELECT hauteur_m, maj_locale FROM metier.support WHERE code = %s", flux["support_local"])[0]
    position, drapeau_armoire = lignes(conn, "SELECT ST_AsText(geom), maj_locale FROM metier.armoire WHERE code = %s", flux["armoire_locale"])[0]
    constat(f"point : {float(puissance)} W alors que la source dit 77 W ; support : {float(hauteur)} m ; armoire déplacée de 10 m conservée")
    assert puissance == 999 and float(hauteur) == 12.5 and position == flux["position"]
    assert drapeau_point and drapeau_support and drapeau_armoire


def test_idempotence(flux, constat):
    """T-FLX-07 : relancer la reprise sans nouveau lot ne réécrit aucune ligne"""
    constat(f"numéros de transaction identiques sur les points, les supports et les armoires : {flux['premiere'] == flux['seconde']}")
    assert flux["premiere"] == flux["seconde"]


def test_bilan_apres_flux(flux, constat):
    """T-FLX-08 : le bilan de reprise reste à zéro après le nouveau lot, et le contrôle ne signale aucune perte"""
    lignes_source, points, ecart = lignes(flux["conn"], "SELECT lignes_source, points_repris, ecart FROM controle.bilan_reprise WHERE gestionnaire = 'NANTES'")[0]
    perte = valeur(flux["conn"], "SELECT count(*) FROM controle.ecart WHERE regle = 'REP_01'")
    constat(f"{lignes_source} lignes = {points} points, écart {ecart}, {perte} écart REP_01")
    assert ecart == 0 and perte == 0


def test_lot_deja_charge(flux, constat):
    """T-FLX-09 : un fichier déjà chargé (même empreinte) n'est pas chargé une seconde fois"""
    n = valeur(flux["conn"], "SELECT count(*) FROM flux.lot WHERE source = 'nantes'")
    constat(flux["rechargement"].strip().splitlines()[-1])
    assert "déjà chargé" in flux["rechargement"] and n == 2
