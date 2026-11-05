"""Verse dans la base les pannes déclarées sur le terrain avec QField.

Le dossier ou le .zip renvoyé par le téléphone contient signalements_terrain.gpkg et les photos. Les lignes passent par
le compte de la collectivité : la base applique son périmètre, signe les fiches et refuse ce qui ne va pas. Un même envoi
importé deux fois ne crée pas de doublon. Le bilan doit tomber juste : reçues = importées + déjà importées + refusées.
Le détail de chaque ligne, motif de refus compris, est écrit dans livrables/terrain/.

Sur le serveur de l'instance du projet, aucun mot de passe n'est demandé. Sur un autre serveur, le mot de passe du compte
vient de PGPASSWORD, de data/comptes_demo.txt, ou de l'écran. Bibliothèque standard seulement, comme 12_copier_base.py.

    python 13_importer_terrain.py retour_telephone.zip
    python 13_importer_terrain.py dossier_du_projet --port 5432 --compte mairie_reze
"""
import argparse
import csv
import datetime as dt
import getpass
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

import config

PSQL = str(config.PG_BIN / "psql.exe")
COMPTES = config.RACINE / "data" / "comptes_demo.txt"
PHOTOS = config.RACINE / "data" / "terrain" / "photos"
RAPPORTS = config.LIVRABLES / "terrain"
GPKG = "signalements_terrain.gpkg"
EXTENSIONS_PHOTO = {".jpg", ".jpeg", ".png"}
CHAMPS = ["uuid_terrain", "point_id", "code_point", "voie", "distance_m", "nature", "description", "photo", "constate_ms"]


def lire_lignes(dossier):
    """Lit une copie : QField peut laisser des écritures dans un fichier -wal, que SQLite reprend à l'ouverture."""
    trouves = list(dossier.rglob(GPKG))
    if len(trouves) != 1:
        sys.exit(f"{len(trouves)} fichier(s) {GPKG} dans cet envoi, un seul attendu. Rien n'a été modifié.")
    source = trouves[0]
    with tempfile.TemporaryDirectory() as temporaire:
        for suffixe in ("", "-wal", "-shm"):
            if Path(f"{source}{suffixe}").exists():
                shutil.copy(f"{source}{suffixe}", Path(temporaire) / f"{GPKG}{suffixe}")
        base = sqlite3.connect(Path(temporaire) / GPKG)
        base.row_factory = sqlite3.Row
        try:
            lignes = [dict(l) for l in base.execute(f"SELECT {', '.join(CHAMPS)} FROM signalements_terrain ORDER BY fid")]
        except sqlite3.DatabaseError as erreur:
            sys.exit(f"{source} ne se lit pas : {erreur}. Rien n'a été modifié.")
        finally:
            base.close()
    return lignes, source.parent


def trouver_photo(racine, valeur):
    """Un chemin venu du téléphone ne doit jamais sortir du dossier reçu."""
    if not valeur:
        return None
    relatif = Path(str(valeur).replace("\\", "/"))
    racine = racine.resolve()
    for candidat in ((racine / relatif).resolve(), racine / "DCIM" / relatif.name):
        if candidat.is_relative_to(racine) and candidat.is_file() and candidat.suffix.lower() in EXTENSIONS_PHOTO:
            return candidat
    return None


def nom_photo(ligne, chemin):
    try:
        return f"{uuid.UUID(str(ligne['uuid_terrain']))}{chemin.suffix.lower()}"
    except ValueError:
        return None  # la base refusera cette ligne : son identifiant n'en est pas un


def preparer(lignes, racine):
    """Le nom de la photo en base dérive de l'identifiant de la ligne : deux téléphones ne peuvent pas se gêner."""
    envoi, sources = [], []
    for ligne in lignes:
        chemin = trouver_photo(racine, ligne["photo"])
        nom = nom_photo(ligne, chemin) if chemin else None
        sources.append(chemin if nom else None)
        envoi.append({"uuid_terrain": ligne["uuid_terrain"], "point_id": ligne["point_id"], "nature": ligne["nature"],
                      "description": (ligne["description"] or "").replace("\x00", "") or None, "constate_ms": ligne["constate_ms"], "photo": nom})
    return envoi, sources


def appeler_base(envoi, port, compte, mot_de_passe):
    # json.dumps n'écrit que de l'ASCII ; seule l'apostrophe reste à doubler pour la chaîne SQL
    litteral = "'" + json.dumps(envoi).replace("'", "''") + "'"
    sql = ("SET standard_conforming_strings = on;\n"
           f"SELECT row_to_json(r) FROM exploitation.importer_signalements_terrain({litteral}::jsonb) r;\n")
    env = dict(os.environ, PGCLIENTENCODING="UTF8")
    env.pop("PGPASSWORD", None)
    if mot_de_passe:
        env["PGPASSWORD"] = mot_de_passe
    r = subprocess.run([PSQL, "-X", "-w", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-h", config.PG_HOST, "-p", str(port), "-U", compte, "-d", config.PG_DB, "-f", "-"],
                       input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if r.returncode:
        if "importer_signalements_terrain" in r.stderr:
            sys.exit(f"Cette base n'a pas encore l'import de terrain, ou ce compte n'y a pas droit. Pour mettre à jour une copie : copier_vers_mon_postgres.bat --remplacer\n{r.stderr.strip()}")
        sys.exit(f"Connexion ou requête refusée, rien n'a été modifié : {r.stderr.strip()}")
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]


def mot_de_passe_du_compte(port, compte):
    if port == config.PG_PORT:
        return None
    if os.environ.get("PGPASSWORD"):
        return os.environ["PGPASSWORD"]
    if COMPTES.exists():
        for ligne in COMPTES.read_text(encoding="utf-8").splitlines():
            nom, separateur, valeur = ligne.partition(" : ")
            if separateur and nom == compte:
                return valeur.strip()
    return getpass.getpass(f"Mot de passe du compte {compte} sur le serveur du port {port} : ")


def importer(chemin, port, compte, dossier_photos=PHOTOS, dossier_rapports=RAPPORTS):
    chemin = Path(chemin)
    if not chemin.exists():
        sys.exit(f"{chemin} n'existe pas. Rien n'a été modifié.")
    with tempfile.TemporaryDirectory() as temporaire:
        if chemin.is_file():
            if not zipfile.is_zipfile(chemin):
                sys.exit(f"{chemin} n'est ni un dossier ni un .zip. Rien n'a été modifié.")
            with zipfile.ZipFile(chemin) as z:
                z.extractall(temporaire)  # extractall neutralise les chemins qui sortiraient du dossier
            dossier = Path(temporaire)
        else:
            dossier = chemin
        lignes, racine = lire_lignes(dossier)
        envoi, sources = preparer(lignes, racine)
        reponses = appeler_base(envoi, port, compte, mot_de_passe_du_compte(port, compte)) if envoi else []
        if len(reponses) != len(lignes):
            sys.exit(f"Bilan faux : {len(lignes)} lignes reçues, {len(reponses)} réponses de la base.")

        dossier_photos = Path(dossier_photos)
        lignes_rapport = []
        for ligne, demande, source, reponse in zip(lignes, envoi, sources, reponses):
            note = []
            if reponse["resultat"] != "refusee" and source:
                dossier_photos.mkdir(parents=True, exist_ok=True)
                if not (dossier_photos / demande["photo"]).exists():
                    shutil.copy(source, dossier_photos / demande["photo"])
            if ligne["photo"] and not source:
                note.append("photo introuvable dans l'envoi")
            if reponse["autres_ouverts"]:
                note.append(f"{reponse['autres_ouverts']} autre(s) signalement(s) ouvert(s) sur ce point")
            lignes_rapport.append({"ligne": reponse["rang"], "resultat": reponse["resultat"], "motif": reponse["motif"] or "", "signalement": reponse["signalement_id"] or "",
                                   "point_lumineux": ligne["code_point"] or "", "rue": ligne["voie"] or "", "distance_m": ligne["distance_m"] if ligne["distance_m"] is not None else "",
                                   "nature": ligne["nature"] or "", "description": ligne["description"] or "", "photo": demande["photo"] or "", "note": " ; ".join(note)})

    bilan = {cle: sum(1 for l in lignes_rapport if l["resultat"] == cle) for cle in ("importee", "deja_importee", "refusee")}
    if sum(bilan.values()) != len(lignes):
        sys.exit(f"Bilan faux : {len(lignes)} lignes reçues, {sum(bilan.values())} comptées.")
    dossier_rapports = Path(dossier_rapports)
    dossier_rapports.mkdir(parents=True, exist_ok=True)
    rapport = dossier_rapports / f"import_{dt.datetime.now():%Y%m%d_%H%M%S}.csv"
    with rapport.open("w", encoding="utf-8-sig", newline="") as f:  # le BOM : Excel lit alors les accents
        ecrivain = csv.DictWriter(f, fieldnames=["ligne", "resultat", "motif", "signalement", "point_lumineux", "rue", "distance_m", "nature", "description", "photo", "note"], delimiter=";")
        ecrivain.writeheader()
        ecrivain.writerows(lignes_rapport)

    print(f"Reçues {len(lignes)} : importées {bilan['importee']}, déjà importées {bilan['deja_importee']}, refusées {bilan['refusee']}.")
    for l in lignes_rapport:
        if l["resultat"] == "refusee":
            print(f"  ligne {l['ligne']} refusée ({l['point_lumineux'] or 'sans point'}) : {l['motif']}")
        elif l["note"]:
            print(f"  ligne {l['ligne']} ({l['point_lumineux']}) : {l['note']}")
    print(f"Détail : {rapport}")
    return {"recues": len(lignes), **bilan, "rapport": str(rapport)}


def choisir_port():
    if not sys.stdin.isatty():
        return config.PG_PORT
    reponse = input(f"Vers quelle base ? 1 = instance du projet (port {config.PG_PORT}), 2 = mon PostgreSQL (port 5432) [1] : ").strip()
    return 5432 if reponse == "2" else config.PG_PORT


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("envoi", nargs="?", help="dossier ou .zip renvoyé par le téléphone")
    p.add_argument("--port", type=int)
    p.add_argument("--compte", default="demo_commune")
    p.add_argument("--photos", default=PHOTOS, help="dossier des photos reçues")
    p.add_argument("--rapports", default=RAPPORTS, help="dossier des comptes rendus d'import")
    args = p.parse_args()
    envoi = args.envoi or input("Glissez ici le dossier ou le .zip reçu du téléphone, puis Entrée : ").strip().strip('"')
    importer(envoi, args.port or choisir_port(), args.compte, args.photos, args.rapports)


if __name__ == "__main__":
    main()
