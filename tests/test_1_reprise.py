"""T-REP : ce qui est entré se retrouve à la sortie, et les décisions de reprise sont tenues."""
import pytest
from conftest import lignes, valeur


@pytest.mark.parametrize("gestionnaire", ["SDE18", "NANTES", "LOIRE"])
def test_bilan_par_source(su, constat, gestionnaire):
    """T-REP-01 : chaque ligne de la source est reprise, fusionnée ou écartée, écart nul"""
    source, points, fusion, ecartees, ecart = lignes(su, """
        SELECT lignes_source, points_repris, lignes_fusionnees, lignes_ecartees, ecart
        FROM controle.bilan_reprise WHERE gestionnaire = %s""", gestionnaire)[0]
    constat(f"{source} lignes = {points} points + {fusion} fusionnées + {ecartees} écartées, écart {ecart}")
    assert ecart == 0
    assert source == points + fusion + ecartees


def test_regles_de_bilan_sans_ecart(su, constat):
    """T-REP-02 : les règles de reprise et de valeurs non prévues ne relèvent aucun écart"""
    n = valeur(su, "SELECT count(*) FROM controle.ecart WHERE regle IN ('REP_01', 'REP_02', 'REP_03', 'REP_04', 'COH_01')")
    constat(f"{n} écart sur REP_01 à REP_04 et COH_01")
    assert n == 0


def test_rejets_motives(su, constat):
    """T-REP-03 : toute ligne non reprise de la publication Loire porte un motif et son contenu"""
    n, sans_motif = lignes(su, "SELECT count(*), count(*) FILTER (WHERE motif IS NULL OR contenu IS NULL) FROM controle.rejet")[0]
    constat(f"{n} lignes en rejet, {sans_motif} sans motif")
    assert n == 43 and sans_motif == 0


def test_codes_uniques(su, constat):
    """T-REP-04 : pas de doublon d'identifiant par gestionnaire, y compris à l'export"""
    doublons = valeur(su, "SELECT count(*) FROM (SELECT gestionnaire, identifiant FROM eclext.pointlumineux GROUP BY 1, 2 HAVING count(*) > 1) d")
    constat(f"{doublons} identifiant en double")
    assert doublons == 0


def test_identifiants_doublons_nantes(su, constat):
    """T-REP-05 : les 4 identifiants de foyer portés par deux objets à Nantes sont gardés, suffixés"""
    n = valeur(su, "SELECT count(*) FROM metier.point_lumineux WHERE code LIKE '%-D2'")
    constat(f"{n} points suffixés -D2")
    assert n == 4


def test_geometries(su, constat):
    """T-REP-06 : géométries valides, en Lambert 93, sur le territoire métropolitain"""
    total, invalides, hors = lignes(su, """
        SELECT count(*), count(*) FILTER (WHERE NOT ST_IsValid(geom) OR ST_SRID(geom) <> 2154),
               count(*) FILTER (WHERE NOT ST_Within(geom, ST_MakeEnvelope(100000, 6000000, 1250000, 7200000, 2154)))
        FROM metier.support""")[0]
    constat(f"{total} supports, {invalides} invalides, {hors} hors de la métropole")
    assert invalides == 0 and hors == 0


def test_date_factice_ignoree(su, constat):
    """T-REP-07 : la date 01/01/1970 du syndicat n'est pas reprise, mais elle est signalée"""
    reprises = valeur(su, "SELECT count(*) FROM metier.support WHERE date_pose = DATE '1970-01-01'")
    signalees = valeur(su, "SELECT count(*) FROM controle.ecart WHERE regle = 'TEM_01'")
    constat(f"{reprises} reprises, {signalees} signalées par TEM_01")
    assert reprises == 0 and signalees > 0


def test_saillie_aberrante(su, constat):
    """T-REP-08 : les saillies probablement en millimètres ne sont pas converties en silence"""
    maximum = valeur(su, "SELECT max(saillie_m) FROM metier.support")
    signalees = valeur(su, "SELECT count(*) FROM controle.ecart WHERE regle = 'VAL_05'")
    constat(f"saillie maximale reprise {maximum} m, {signalees} valeurs signalées par VAL_05")
    assert maximum <= 20 and signalees == 877


def test_correspondances_vers_listes(su, constat):
    """T-REP-09 : toute valeur cible des correspondances existe dans la liste du standard"""
    listes = {"typeSource": "type_source", "structure": "structure_luminaire", "support": "support_luminaire", "usage": "usage"}
    orphelines = []
    for attribut, table in listes.items():
        orphelines += lignes(su, f"""SELECT source, valeur_source, valeur_cible FROM ref.correspondance c
                                     WHERE attribut_cible = %s AND valeur_cible IS NOT NULL
                                       AND valeur_cible NOT IN (SELECT code FROM ref.{table})""", attribut)
    total = valeur(su, "SELECT count(*) FROM ref.correspondance")
    constat(f"{total} correspondances, {len(orphelines)} orphelines")
    assert not orphelines


def test_hypotheses_tracees(su, constat):
    """T-REP-10 : l'hypothèse « un point par support » du syndicat reste visible sur chaque point"""
    hypothese, total = lignes(su, """SELECT count(*) FILTER (WHERE p.un_point_par_support), count(*) FROM metier.point_lumineux p
                                     JOIN metier.gestionnaire g ON g.id = p.gestionnaire_id WHERE g.code = 'SDE18'""")[0]
    constat(f"{hypothese} points sur {total} portent l'hypothèse")
    assert hypothese == total


def test_rapprochement(su, constat):
    """T-REP-11 : le rapprochement des deux bases du Cher classe chaque objet"""
    statuts = dict(lignes(su, "SELECT statut, count(*) FROM controle.rapprochement GROUP BY 1"))
    constat(statuts)
    assert statuts["apparie"] == 5347 and statuts["recode_probable"] == 14 and statuts["absent_syndicat"] == 11
    assert valeur(su, "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY distance_m) FROM controle.rapprochement WHERE statut = 'apparie'") == 0
