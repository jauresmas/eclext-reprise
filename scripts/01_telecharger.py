"""Étape 1 : collecte des sources ouvertes, avec manifeste (adresse, date, taille, empreinte).

Chaque collecte est rangée dans data/sources/<source>/<AAAAMMJJ>/ ; l'adresse du fichier est
relue dans le catalogue data.gouv.fr. Le manifeste permet de savoir à quelle version des
données correspond un résultat, et de ne recharger que ce qui a changé.

    python 01_telecharger.py [--force]
"""
import argparse
import datetime as dt
import hashlib
import json
import shutil
import urllib.request

import config
from outils import log


def lire_url(url, chemin=None):
    requete = urllib.request.Request(url, headers={"User-Agent": config.CLIENT_HTTP})
    with urllib.request.urlopen(requete, timeout=240) as reponse:
        if chemin is None:
            return reponse.read()
        with open(chemin, "wb") as sortie:
            shutil.copyfileobj(reponse, sortie)


def empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def collecter_source(cle, src, jour, force):
    dossier = config.SOURCES / cle / jour
    fichier = dossier / src["fichier"]
    manifeste = dossier / "manifeste.json"
    if manifeste.exists() and not force:
        log(f"{cle} : déjà collecté le {jour}")
        return
    dossier.mkdir(parents=True, exist_ok=True)
    jeu = json.loads(lire_url(f"https://www.data.gouv.fr/api/1/datasets/{src['jeu']}/"))
    ressources = [r for r in jeu["resources"] if (r.get("format") or "").lower() == src["format"]]
    if not ressources:
        raise RuntimeError(f"{cle} : aucune ressource {src['format']} au catalogue")
    url = ressources[0]["url"]
    log(f"{cle} : téléchargement de {url[:90]}")
    lire_url(url, fichier)
    manifeste.write_text(json.dumps({
        "source": cle, "titre": src["titre"], "producteur": src["producteur"],
        "page": jeu.get("page"), "licence": jeu.get("license"), "maj_catalogue": jeu.get("last_update"),
        "url": url, "date_collecte": jour, "fichier": fichier.name,
        "taille": fichier.stat().st_size, "sha256": empreinte(fichier),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"{cle} : {fichier.stat().st_size / 1e6:.1f} Mo")


def collecter_communes(force):
    dossier = config.SOURCES / "communes"
    dossier.mkdir(parents=True, exist_ok=True)
    for cle, url in config.COMMUNES.items():
        fichier = dossier / f"{cle}.geojson"
        if fichier.exists() and not force:
            continue
        lire_url(url, fichier)
        n = len(json.loads(fichier.read_text(encoding="utf-8"))["features"])
        log(f"communes {cle} : {n}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true", help="retélécharge même si la collecte du jour existe")
    args = p.parse_args()
    jour = dt.date.today().strftime("%Y%m%d")
    for cle, src in config.SOURCES_OUVERTES.items():
        collecter_source(cle, src, jour, args.force)
    collecter_communes(args.force)
