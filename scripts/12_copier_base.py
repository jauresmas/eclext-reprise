"""Copie la base du projet dans un serveur PostgreSQL déjà installé (par défaut localhost:5432, compte postgres).

La base d'origine reste en place : la chaîne et les tests continuent de tourner sur l'instance du projet.
Le serveur doit avoir la même version de PostGIS, ce qui est le cas s'il vient de la même installation.

Le mot de passe du serveur est demandé à l'écran. Il n'est ni affiché ni écrit, seuls les outils PostgreSQL le reçoivent.
Une base eclext déjà présente n'est remplacée qu'avec --remplacer.

Le script crée aussi, sur ce serveur, les rôles ep_* et les comptes demo_*. Les comptes reçoivent un mot de passe tiré
au hasard, écrit dans data/comptes_demo.txt (non versionné). Les projets QGIS qui visent ce serveur sont écrits dans
projets/mon_postgres/ : QGIS demande le mot de passe du compte à l'ouverture.

    python 12_copier_base.py
    python 12_copier_base.py --port 5433 --compte moi
    python 12_copier_base.py --remplacer
"""
import argparse
import getpass
import os
import secrets
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import config

PSQL, PG_DUMP, PG_RESTORE = (str(config.PG_BIN / f"{outil}.exe") for outil in ("psql", "pg_dump", "pg_restore"))
COMPTES = config.RACINE / "data" / "comptes_demo.txt"
PROJETS = config.RACINE / "projets"

# Une ligne par table, avec son nombre de lignes. La vue système ne suffit pas : ses comptes sont des estimations.
COMPTAGE = """
SELECT n.nspname || '.' || c.relname || ' ' ||
       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I', n.nspname, c.relname), false, true, '')))[1]::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1
"""


def environnement(mot_de_passe=None):
    env = dict(os.environ, PGCLIENTENCODING="UTF8")
    env.pop("PGPASSWORD", None)
    if mot_de_passe:
        env["PGPASSWORD"] = mot_de_passe
    return env


def psql(sql, port, compte, base, mot_de_passe=None):
    """Le SQL passe par l'entrée standard : sous Windows, un argument de ligne de commande abîme les accents."""
    r = subprocess.run([PSQL, "-X", "-w", "-At", "-v", "ON_ERROR_STOP=1", "-h", config.PG_HOST, "-p", str(port), "-U", compte, "-d", base, "-f", "-"],
                       input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environnement(mot_de_passe))
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def source(sql):
    return psql(sql, config.PG_PORT, config.PG_SUPERUSER, config.PG_DB)


def demander_mot_de_passe(port, compte):
    if os.environ.get("PGPASSWORD"):
        essais = [os.environ["PGPASSWORD"]]
    else:
        essais = (getpass.getpass(f"Mot de passe du compte {compte} sur le serveur du port {port} : ") for _ in range(3))
    for mot_de_passe in essais:
        try:
            if psql("SELECT rolsuper FROM pg_roles WHERE rolname = current_user", port, compte, "postgres", mot_de_passe) != "t":
                sys.exit(f"Le compte {compte} n'est pas superutilisateur : il ne peut pas installer PostGIS ni créer les rôles.")
            return mot_de_passe
        except RuntimeError as erreur:
            print(f"Connexion refusée : {erreur}")
    sys.exit("Rien n'a été modifié.")


def creer_roles(port, compte, mot_de_passe):
    """Les rôles appartiennent au serveur, pas à la base : une sauvegarde de la base ne les emporte pas."""
    lignes = source("""SELECT r.rolname, r.rolcanlogin, coalesce(string_agg(g.rolname, ','), '')
                       FROM pg_roles r
                       LEFT JOIN pg_auth_members m ON m.member = r.oid
                       LEFT JOIN pg_roles g ON g.oid = m.roleid
                       WHERE r.rolname ~ '^(ep|demo)_'
                       GROUP BY 1, 2 ORDER BY 2, 1""")
    instructions, comptes = [], {}
    for ligne in lignes.splitlines():
        role, connexion, groupes = ligne.split("|")
        nature = "LOGIN" if connexion == "t" else "NOLOGIN"
        instructions.append(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN CREATE ROLE {role} {nature}; END IF; END $$;")
        if connexion == "t":
            comptes[role] = secrets.token_urlsafe(12)
            instructions.append(f"ALTER ROLE {role} PASSWORD '{comptes[role]}';")
        instructions.extend(f"GRANT {groupe} TO {role};" for groupe in groupes.split(",") if groupe)
    psql("\n".join(instructions), port, compte, "postgres", mot_de_passe)
    COMPTES.write_text("Comptes de démonstration de la base eclext sur le serveur du port "
                       f"{port}. À ne pas versionner.\n\n" + "".join(f"{c} : {m}\n" for c, m in comptes.items()), encoding="utf-8")
    return comptes


def copier(port, compte, mot_de_passe):
    with tempfile.TemporaryDirectory() as dossier:
        sauvegarde = Path(dossier) / "eclext.dump"
        print("Sauvegarde de la base du projet...", flush=True)
        subprocess.run([PG_DUMP, "-Fc", "-w", "-h", config.PG_HOST, "-p", str(config.PG_PORT), "-U", config.PG_SUPERUSER, "-f", str(sauvegarde), config.PG_DB],
                       check=True, env=environnement())
        print(f"Restauration sur le port {port}...", flush=True)
        # --create garde l'encodage et le classement de l'origine ; --no-owner donne tout au compte qui restaure
        r = subprocess.run([PG_RESTORE, "-w", "--create", "--no-owner", "--exit-on-error", "-h", config.PG_HOST, "-p", str(port), "-U", compte, "-d", "postgres", str(sauvegarde)],
                           capture_output=True, text=True, errors="replace", env=environnement(mot_de_passe))
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    psql("ANALYZE", port, compte, config.PG_DB, mot_de_passe)


def verifier(port, compte, mot_de_passe, comptes):
    """Mêmes tables, mêmes lignes ; et le périmètre d'un compte tient toujours sur le nouveau serveur."""
    origine, copie = (dict(ligne.rsplit(" ", 1) for ligne in texte.splitlines())
                      for texte in (source(COMPTAGE), psql(COMPTAGE, port, compte, config.PG_DB, mot_de_passe)))
    differences = sorted(t for t in origine.keys() | copie.keys() if origine.get(t) != copie.get(t))
    if differences:
        raise RuntimeError(f"Tables différentes entre l'origine et la copie : {differences}")
    print(f"Contrôle : {len(copie)} tables, {sum(int(n) for n in copie.values())} lignes, identiques à l'origine.")

    attendu = psql("""SELECT count(*) FROM metier.point_lumineux p JOIN admin.habilitation h ON p.insee = ANY(h.communes)
                      WHERE h.login = 'demo_commune'""", port, compte, config.PG_DB, mot_de_passe)
    total = psql("SELECT count(*) FROM metier.point_lumineux", port, compte, config.PG_DB, mot_de_passe)
    vu = psql("SELECT count(*) FROM metier.point_lumineux", port, "demo_commune", config.PG_DB, comptes["demo_commune"])
    if vu != attendu or vu == total:
        raise RuntimeError(f"Périmètre non respecté : demo_commune voit {vu} points, {attendu} attendus sur {total}.")
    print(f"Contrôle : le compte demo_commune voit {vu} points sur {total}, son périmètre tient.")


def projets_qgis(port):
    """Mêmes projets, seul le port change. La recherche porte sur « port=5436 » : ce nombre peut exister ailleurs dans le projet."""
    dossier = PROJETS / "mon_postgres"
    dossier.mkdir(exist_ok=True)
    for projet in sorted(PROJETS.glob("*.qgz")):
        with zipfile.ZipFile(projet) as lecture, zipfile.ZipFile(dossier / projet.name, "w", zipfile.ZIP_DEFLATED) as ecriture:
            for nom in lecture.namelist():
                contenu = lecture.read(nom)
                if nom.endswith(".qgs"):
                    contenu = contenu.replace(f"port={config.PG_PORT}".encode(), f"port={port}".encode())
                ecriture.writestr(nom, contenu)
    print(f"Projets QGIS pour ce serveur : {dossier}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--compte", default="postgres")
    p.add_argument("--remplacer", action="store_true", help="efface la base eclext déjà présente sur ce serveur")
    args = p.parse_args()
    if args.port == config.PG_PORT:
        sys.exit("Ce port est celui de l'instance du projet : indiquez un autre serveur.")
    sys.stdout.reconfigure(errors="replace")

    try:
        source("SELECT 1")
    except RuntimeError as erreur:
        sys.exit(f"La base du projet ne répond pas : lancez demarrer_base.bat.\n{erreur}")
    mot_de_passe = demander_mot_de_passe(args.port, args.compte)
    if psql(f"SELECT 1 FROM pg_database WHERE datname = '{config.PG_DB}'", args.port, args.compte, "postgres", mot_de_passe):
        if not args.remplacer:
            sys.exit(f"Une base {config.PG_DB} existe déjà sur ce serveur. Rien n'a été modifié. Pour l'effacer et la remplacer : --remplacer")
        print(f"Base {config.PG_DB} existante : effacée.", flush=True)
        psql(f"DROP DATABASE {config.PG_DB} WITH (FORCE)", args.port, args.compte, "postgres", mot_de_passe)

    try:
        comptes = creer_roles(args.port, args.compte, mot_de_passe)
        copier(args.port, args.compte, mot_de_passe)
        verifier(args.port, args.compte, mot_de_passe, comptes)
    except (RuntimeError, subprocess.CalledProcessError) as erreur:
        sys.exit(f"Échec de la copie : {erreur}")
    projets_qgis(args.port)
    print(f"Terminé. Base {config.PG_DB} sur {config.PG_HOST}:{args.port}. Mots de passe des comptes de démonstration : {COMPTES}")


if __name__ == "__main__":
    main()
