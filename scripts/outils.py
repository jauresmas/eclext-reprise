"""Fonctions communes de la chaîne : journal, psql, connexion, formats français."""
import os
import subprocess
import time
from contextlib import contextmanager

import config
import psycopg2


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def pg_env():
    env = os.environ.copy()
    env.update(PGHOST=config.PG_HOST, PGPORT=str(config.PG_PORT), PGCLIENTENCODING="UTF8",
               LC_ALL="C", LANG="C")  # messages de psql en ASCII, quelle que soit la langue du poste
    if config.PROJ_LIB_POSTGIS:  # le serveur PostGIS a besoin de sa propre base PROJ
        env["PROJ_LIB"] = config.PROJ_LIB_POSTGIS
    return env


def psql(sql=None, fichier=None, base=None):
    """Exécute du SQL avec psql (arrêt à la première erreur) ; renvoie la sortie texte."""
    cmd = [str(config.PG_BIN / "psql.exe"), "-X", "-q", "-v", "ON_ERROR_STOP=1",
           "-d", base or config.PG_DB, "-U", config.PG_SUPERUSER]
    if fichier:
        cmd += ["-f", str(fichier)]
    else:
        # le SQL passe par l'entrée standard en UTF-8 : en argument de ligne de commande,
        # Windows le convertirait dans la page de code locale
        cmd += ["-At"]
    res = subprocess.run(cmd, env=pg_env(), capture_output=True, text=True, encoding="utf-8",
                         errors="replace", input=None if fichier else sql)
    if res.returncode != 0:
        raise RuntimeError(f"psql a échoué ({fichier or sql[:80]}) :\n{res.stderr}")
    return res.stdout.strip()


def executer_sql(*noms):
    """Exécute des fichiers du dossier sql/ dans l'ordre donné."""
    for nom in noms:
        debut = time.time()
        psql(fichier=config.SQL / nom)
        log(f"  {nom} ({time.time() - debut:.1f} s)")


def connexion(utilisateur=None):
    return psycopg2.connect(host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB,
                            user=utilisateur or config.PG_SUPERUSER)


@contextmanager
def curseur(utilisateur=None):
    """Curseur dans une transaction validée à la sortie du bloc."""
    conn = connexion(utilisateur)
    try:
        with conn, conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def fr(nombre, decimales=0):
    """Nombre à la française : espace insécable pour les milliers, virgule décimale."""
    if nombre is None:
        return "n. d."
    texte = f"{nombre:,.{decimales}f}"
    return texte.replace(",", " ").replace(".", ",")


def pct(valeur, decimales=1):
    return "n. d." if valeur is None else f"{fr(valeur, decimales)} %"
