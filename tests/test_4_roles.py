"""T-ROL : chaque compte ne voit et ne modifie que son périmètre, et c'est la base qui l'applique."""
import psycopg2
import pytest
from conftest import executer, lignes, valeur

REFUSES = (psycopg2.errors.InsufficientPrivilege,)


@pytest.mark.parametrize("login, communes", [("demo_commune", {"44143"}), ("demo_entreprise", {"44143", "44020"}), ("demo_entreprise_b", {"44215"})])
@pytest.mark.parametrize("table", ["metier.point_lumineux", "metier.support", "metier.armoire", "controle.ecart"])
def test_perimetre_en_lecture(compte, su, constat, login, communes, table):
    """T-ROL-01 : un compte ne lit que les communes de son périmètre"""
    conn = compte(login)
    vues = {r[0] for r in lignes(conn, f"SELECT DISTINCT insee FROM {table}")}
    attendu = valeur(su, f"SELECT count(*) FROM {table} WHERE insee = ANY(%s)", list(communes))
    n = valeur(conn, f"SELECT count(*) FROM {table}")
    constat(f"{n} lignes, communes {sorted(vues)}")
    assert vues <= communes
    assert n == attendu


def test_administrateur_voit_tout(compte, su, constat):
    """T-ROL-02 : l'administrateur voit tout le territoire"""
    n = valeur(compte("demo_admin"), "SELECT count(*) FROM metier.point_lumineux")
    constat(f"{n} points")
    assert n == valeur(su, "SELECT count(*) FROM metier.point_lumineux")


def test_entreprise_voit_ses_interventions(compte, constat):
    """T-ROL-03 : une entreprise ne voit que ses interventions, pas celles d'une autre"""
    a = lignes(compte("demo_entreprise"), "SELECT DISTINCT entreprise_id FROM exploitation.intervention")
    b = lignes(compte("demo_entreprise_b"), "SELECT DISTINCT entreprise_id FROM exploitation.intervention")
    constat(f"entreprise A : {a}, entreprise B : {b}")
    assert len(a) == 1 and len(b) == 1 and a != b


@pytest.mark.parametrize("login", ["demo_commune", "demo_entreprise", "demo_lecture"])
@pytest.mark.parametrize("ordre", [
    "UPDATE metier.point_lumineux SET puissance_w = 1",
    "DELETE FROM metier.support",
    "INSERT INTO exploitation.intervention (point_id, nature, insee, geom) SELECT id, 'CONTROLE', insee, geom FROM metier.point_lumineux LIMIT 1",
    "DELETE FROM exploitation.signalement",
    "DROP TABLE exploitation.signalement",
])
def test_ecritures_interdites(compte, constat, login, ordre):
    """T-ROL-04 : hors de sa fiche, un compte ne peut ni écrire ni supprimer"""
    with pytest.raises(REFUSES):
        executer(compte(login), ordre)
    constat("refusé par la base")


def test_lecture_format_echange_seulement(compte, constat):
    """T-ROL-05 : le compte de lecture lit le format EclExt, pas les tables de travail"""
    conn = compte("demo_lecture")
    n = valeur(conn, "SELECT count(*) FROM eclext.pointlumineux")
    conn.rollback()
    constat(f"{n} points au format d'échange")
    assert n > 0
    for table in ("metier.point_lumineux", "exploitation.intervention", "controle.ecart", "admin.habilitation", "audit.journal"):
        with pytest.raises(REFUSES):
            valeur(conn, f"SELECT count(*) FROM {table}")
        conn.rollback()


def test_collectivite_signale_chez_elle(compte, su, constat):
    """T-ROL-06 : une collectivité signale dans sa commune, jamais ailleurs"""
    conn = compte("demo_commune")
    chez_elle = valeur(su, "SELECT min(id) FROM metier.point_lumineux WHERE insee = '44143'")
    ailleurs = valeur(su, "SELECT min(id) FROM metier.point_lumineux WHERE insee = '44215'")
    sql = "INSERT INTO exploitation.signalement (point_id, description, insee, geom) VALUES (%s, 'Essai', '44143', ST_SetSRID(ST_Point(0, 0), 2154)) RETURNING insee, declarant"
    insee, declarant = lignes(conn, sql, chez_elle)[0]
    constat(f"accepté à {insee} par {declarant}")
    assert insee == "44143" and declarant == "demo_commune"
    conn.rollback()
    # La commune et la position viennent de l'objet : déclarer une fausse commune ne contourne pas le périmètre
    with pytest.raises(REFUSES):
        lignes(conn, sql, ailleurs)


def test_entreprise_colonnes(compte, su, constat):
    """T-ROL-07 : une entreprise ne change ni la nature, ni le titulaire, ni l'objet de l'intervention"""
    conn = compte("demo_entreprise")
    cible = valeur(conn, "SELECT min(id) FROM exploitation.intervention WHERE etat = 'A_PLANIFIER'")
    conn.rollback()
    for colonne, v in (("nature", "CONTROLE"), ("entreprise_id", 2), ("point_id", 1)):
        with pytest.raises(REFUSES):
            executer(conn, f"UPDATE exploitation.intervention SET {colonne} = %s WHERE id = %s", v, cible)
        conn.rollback()
    assert executer(conn, "UPDATE exploitation.intervention SET compte_rendu = 'Passage prévu' WHERE id = %s", cible) == 1
    constat("nature, titulaire et objet refusés ; compte rendu accepté")


def test_entreprise_sans_prise_sur_les_autres(compte, su, constat):
    """T-ROL-08 : une entreprise ne peut pas modifier l'intervention d'une autre"""
    autre = valeur(su, "SELECT min(id) FROM exploitation.intervention WHERE entreprise_id = (SELECT id FROM admin.entreprise WHERE nom LIKE 'Entreprise B%')")
    n = executer(compte("demo_entreprise"), "UPDATE exploitation.intervention SET compte_rendu = 'Intrusion' WHERE id = %s", autre)
    constat(f"{n} ligne modifiée")
    assert n == 0


def test_comptes_sans_mot_de_passe_ni_superutilisateur(su, constat):
    """T-ROL-09 : aucun compte de démonstration n'est superutilisateur ni propriétaire d'objet"""
    roles = lignes(su, "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname LIKE 'demo_%' OR rolname LIKE 'ep_%'")
    constat(f"{len(roles)} rôles vérifiés")
    assert roles and not any(r[1] or r[2] or r[3] for r in roles)
    assert valeur(su, "SELECT count(*) FROM pg_tables WHERE tableowner LIKE 'demo_%' OR tableowner LIKE 'ep_%'") == 0


def test_creation_de_compte_reservee(compte, constat):
    """T-ROL-10 : un profil ordinaire ne peut pas créer de compte"""
    with pytest.raises(REFUSES):
        valeur(compte("demo_commune"), "SELECT admin.creer_compte('intrus', 'ep_administrateur')")
    constat("refusé par la base")
