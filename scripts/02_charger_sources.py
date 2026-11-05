"""Étape 2 : chargement brut des sources dans le schéma src, sans aucune transformation.

Toutes les colonnes restent en texte et chaque ligne garde son numéro dans le fichier d'origine :
c'est la référence à laquelle la reprise sera comparée. Un lot déjà chargé (même empreinte) n'est
pas rechargé. Le différentiel avec le lot précédent est calculé par flux.comparer_lots.

    python 02_charger_sources.py [--dossier <collecte>] [--source sde18]
"""
import argparse
import csv
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import config
from outils import connexion, curseur, log

csv.field_size_limit(10**8)

CLES_DIFFERENTIEL = {
    "sde18": ("gid",),
    "ccf": ("commune", "code_point_lumineux"),
    "nantes": ("identifiant_du_foyer", "ligne_doublon"),
    "loire": ("ligne",),  # le fichier n'a pas de clé fiable sur ses lignes coupées
}


def colonne(nom):
    """Nom de colonne SQL tiré de l'en-tête du fichier."""
    nom = unicodedata.normalize("NFD", nom).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", nom).strip("_")


def lire_sde18(chemin):
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    lignes = []
    for f in donnees["features"]:
        ligne = {colonne(k): v for k, v in f["properties"].items()}
        lon, lat = f["geometry"]["coordinates"][:2]
        ligne["lon"], ligne["lat"] = repr(lon), repr(lat)
        lignes.append(ligne)
    return lignes


def lire_csv(chemin, separateur, guillemets=True, encodage="utf-8-sig"):
    # newline="" : un saut de ligne dans un champ reste visible, il n'est jamais corrigé ici
    with open(chemin, encoding=encodage, errors="replace", newline="") as f:
        lecteur = csv.reader(f, delimiter=separateur, quoting=csv.QUOTE_MINIMAL if guillemets else csv.QUOTE_NONE)
        entete = [colonne(c) for c in next(lecteur)]
        return [dict(zip(entete, ligne)) for ligne in lecteur]


def lire_nantes(chemin):
    lignes = lire_csv(chemin, ";")
    vus = {}
    for ligne in lignes:  # certaines lignes portent le même identifiant : on les garde toutes
        cle = ligne["identifiant_du_foyer"]
        vus[cle] = vus.get(cle, 0) + 1
        ligne["ligne_doublon"] = str(vus[cle])
    return lignes


LECTEURS = {
    "sde18": lire_sde18,
    "ccf": lambda c: lire_csv(c, ";"),
    "nantes": lire_nantes,
    # guillemets inactifs : le fichier contient des guillemets isolés qui avaleraient des lignes
    "loire": lambda c: lire_csv(c, "\t", guillemets=False),
}


def creer_table(cur, source, colonnes):
    cols = ", ".join(f'"{c}" text' for c in colonnes)
    cur.execute(f"""CREATE TABLE IF NOT EXISTS src.{source} (
        lot_id integer NOT NULL REFERENCES flux.lot(id), ligne integer NOT NULL, {cols},
        PRIMARY KEY (lot_id, ligne))""")


def valeur_copy(v):
    if v is None:
        return r"\N"
    return str(v).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def charger(source, dossier):
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    with curseur() as cur:
        cur.execute("SELECT id FROM flux.lot WHERE source = %s AND sha256 = %s", (source, manifeste["sha256"]))
        existant = cur.fetchone()
    if existant:
        log(f"{source} : lot {existant[0]} déjà chargé (même empreinte)")
        return existant[0]
    lignes = LECTEURS[source](dossier / manifeste["fichier"])
    colonnes = []
    for ligne in lignes:  # ordre d'apparition, toutes colonnes confondues
        for c in ligne:
            if c not in colonnes:
                colonnes.append(c)
    conn = connexion()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO flux.lot (source, date_collecte, url, page, licence, sha256, taille, nb_lignes)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        (source, manifeste["date_collecte"], manifeste["url"], manifeste.get("page"),
                         manifeste.get("licence"), manifeste["sha256"], manifeste["taille"], len(lignes)))
            lot = cur.fetchone()[0]
            creer_table(cur, source, colonnes)
            tampon = io.StringIO()
            for i, ligne in enumerate(lignes, start=1):
                tampon.write("\t".join([str(lot), str(i)] + [valeur_copy(ligne.get(c)) for c in colonnes]) + "\n")
            tampon.seek(0)
            noms = ", ".join(["lot_id", "ligne"] + [f'"{c}"' for c in colonnes])
            cur.copy_expert(f"COPY src.{source} ({noms}) FROM STDIN", tampon)
            cur.execute("UPDATE flux.lot SET courant = (id = %s) WHERE source = %s", (lot, source))
            cur.execute("SELECT flux.comparer_lots(%s, %s)", (source, list(CLES_DIFFERENTIEL[source])))
    finally:
        conn.close()
    log(f"{source} : lot {lot}, {len(lignes)} lignes")
    return lot


def charger_communes():
    with curseur() as cur:
        cur.execute("SELECT count(*) FROM ref.commune")
        if cur.fetchone()[0]:
            return
        n = 0
        for fichier in sorted((config.SOURCES / "communes").glob("*.geojson")):
            for f in json.loads(fichier.read_text(encoding="utf-8"))["features"]:
                p = f["properties"]
                cur.execute("""INSERT INTO ref.commune (insee, nom, departement, epci, geom)
                    VALUES (%s, %s, %s, %s, ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 2154)))
                    ON CONFLICT (insee) DO NOTHING""",
                            (p["code"], p["nom"], p["codeDepartement"], p.get("codeEpci"), json.dumps(f["geometry"])))
                n += cur.rowcount
    log(f"communes : {n}")


def derniere_collecte(source):
    dossiers = sorted(d for d in (config.SOURCES / source).iterdir() if (d / "manifeste.json").exists())
    if not dossiers:
        sys.exit(f"{source} : aucune collecte, lancer 01_telecharger.py")
    return dossiers[-1]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=list(config.SOURCES_OUVERTES), help="une seule source")
    p.add_argument("--dossier", help="dossier de collecte à charger (avec --source)")
    args = p.parse_args()
    charger_communes()
    for cle in ([args.source] if args.source else config.SOURCES_OUVERTES):
        charger(cle, Path(args.dossier) if args.dossier else derniere_collecte(cle))
