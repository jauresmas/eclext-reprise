"""Outils communs du cahier de recette.

Chaque test commence par une docstring « T-XXX-00 : ce qui est vérifié ». Le numéro, le libellé, le résultat
et le constat (fixture `constat`) sont écrits dans livrables/recette/resultats_tests.json, que l'étape 10
transforme en cahier de recette. Les écritures sont annulées à la fin de chaque test.
"""
import json
import sys
from pathlib import Path

import psycopg2
import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
import config  # noqa: E402

_RESULTATS = []


def connecter(login=config.PG_SUPERUSER, base=config.PG_DB):
    return psycopg2.connect(host=config.PG_HOST, port=config.PG_PORT, dbname=base, user=login)


def valeur(conn, requete, *parametres):
    with conn.cursor() as cur:
        cur.execute(requete, parametres or None)
        ligne = cur.fetchone()
    return ligne[0] if ligne else None


def lignes(conn, requete, *parametres):
    with conn.cursor() as cur:
        cur.execute(requete, parametres or None)
        return cur.fetchall()


def executer(conn, requete, *parametres):
    with conn.cursor() as cur:
        cur.execute(requete, parametres or None)
        return cur.rowcount


@pytest.fixture
def su():
    """Connexion propriétaire, annulée à la fin du test."""
    conn = connecter()
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def compte():
    """Connexion avec le compte d'un profil, annulée à la fin du test."""
    ouvertes = []

    def ouvrir(login):
        conn = connecter(login)
        ouvertes.append(conn)
        return conn
    yield ouvrir
    for conn in ouvertes:
        conn.rollback()
        conn.close()


@pytest.fixture
def constat(request):
    def noter(texte):
        request.node.user_properties.append(("constat", str(texte)))
    return noter


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultat = yield
    rapport = resultat.get_result()
    if rapport.when == "call" or (rapport.when == "setup" and rapport.outcome != "passed"):
        doc = (getattr(item.function, "__doc__", "") or "").strip().splitlines()
        numero, _, libelle = (doc[0] if doc else item.name).partition(" : ")
        parametre = item.callspec.id if hasattr(item, "callspec") else ""
        _RESULTATS.append({
            "numero": numero + (f" [{parametre}]" if parametre else ""),
            "libelle": libelle,
            "resultat": {"passed": "réussi", "failed": "échoué", "skipped": "non exécuté"}[rapport.outcome],
            "constat": " ; ".join(v for k, v in item.user_properties if k == "constat"),
            "detail": str(rapport.longrepr)[-600:] if rapport.outcome != "passed" else "",
            "duree_s": round(rapport.duration, 2),
        })


def pytest_sessionfinish(session):
    sortie = RACINE / "livrables" / "recette" / "resultats_tests.json"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(_RESULTATS, ensure_ascii=False, indent=1), encoding="utf-8")
