"""T-STR : la base refuse ce que le géostandard interdit. Chaque écriture est annulée."""
import psycopg2
import pytest
from conftest import valeur

POINT = "(SELECT min(id) FROM metier.point_lumineux WHERE insee = '44143')"


@pytest.mark.parametrize("colonne, mauvaise_valeur", [
    ("type_source", "XENON"),
    ("usage", "Z9"),
    ("structure", "ABC"),
    ("statut", "en panne"),
    ("temperature_couleur", 500),
    ("puissance_w", -10),
])
def test_valeur_refusee_sur_le_point(su, constat, colonne, mauvaise_valeur):
    """T-STR-01 : une valeur hors liste ou hors bornes est refusée sur le point lumineux"""
    with pytest.raises((psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation, psycopg2.errors.StringDataRightTruncation)) as erreur:
        with su.cursor() as cur:
            cur.execute(f"UPDATE metier.point_lumineux SET {colonne} = %s WHERE id = {POINT}", (mauvaise_valeur,))
    constat(type(erreur.value).__name__)


@pytest.mark.parametrize("colonne, mauvaise_valeur", [
    ("type_support", "XYZ"),
    ("hauteur_m", 90),
    ("etat", "cassé"),
    ("date_pose", "1800-01-01"),
])
def test_valeur_refusee_sur_le_support(su, constat, colonne, mauvaise_valeur):
    """T-STR-02 : une valeur hors liste ou hors bornes est refusée sur le support"""
    with pytest.raises((psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation, psycopg2.errors.StringDataRightTruncation, psycopg2.errors.NumericValueOutOfRange)) as erreur:
        with su.cursor() as cur:
            cur.execute(f"UPDATE metier.support SET {colonne} = %s WHERE id = (SELECT min(id) FROM metier.support)", (mauvaise_valeur,))
    constat(type(erreur.value).__name__)


def test_identifiant_en_double(su, constat):
    """T-STR-03 : deux points d'un même gestionnaire ne partagent pas un identifiant"""
    with pytest.raises(psycopg2.errors.UniqueViolation):
        with su.cursor() as cur:
            cur.execute("""UPDATE metier.point_lumineux SET code = (SELECT code FROM metier.point_lumineux ORDER BY id LIMIT 1)
                           WHERE id = (SELECT id FROM metier.point_lumineux ORDER BY id OFFSET 1 LIMIT 1)""")
    constat("identifiant refusé")


def test_point_sans_support(su, constat):
    """T-STR-04 : un point lumineux sans support, ou sans commune, est refusé"""
    for colonne in ("support_id", "insee"):
        with pytest.raises(psycopg2.errors.NotNullViolation):
            with su.cursor() as cur:
                cur.execute(f"UPDATE metier.point_lumineux SET {colonne} = NULL WHERE id = {POINT}")
        su.rollback()
    constat("support et commune obligatoires")


def test_support_supprime_avec_point(su, constat):
    """T-STR-05 : un support qui porte un point ne peut pas être supprimé"""
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        with su.cursor() as cur:
            cur.execute(f"DELETE FROM metier.support WHERE id = (SELECT support_id FROM metier.point_lumineux WHERE id = {POINT})")
    constat("suppression refusée")


@pytest.mark.parametrize("heure, attendu", [("22:00HL", True), ("06:30TU", True), ("+30MN", True), ("24:00HL", False), ("22h00", False),
                                            ("22:60HL", False), ("2200", False)])
def test_format_heure(su, constat, heure, attendu):
    """T-STR-06 : le format d'heure de la section 3.5 du standard est contrôlé"""
    obtenu = valeur(su, "SELECT coalesce(ref.heure_eclext_valide(%s), false)", heure)
    constat(f"{heure} : {obtenu}")
    assert obtenu is attendu


@pytest.mark.parametrize("entree, attendu", [("Éclairage public", "Eclairage_public"), ("a/b c", "a_b_c"), ("LED-3000.k_v2", "LED-3000.k_v2")])
def test_chaines_standard(su, constat, entree, attendu):
    """T-STR-07 : les chaînes exportées n'ont que les caractères permis par la section 4.4"""
    obtenu = valeur(su, "SELECT eclext.chaine(%s)", entree)
    constat(f"{entree} donne {obtenu}")
    assert obtenu == attendu


def test_listes_du_standard(su, constat):
    """T-STR-08 : les listes de valeurs ont le nombre de codes du standard, avec XX et AU là où il les prévoit"""
    attendu = {"usage": 14, "type_source": 12, "structure_luminaire": 12, "support_luminaire": 11, "eclairage_adaptatif": 4, "statut_installation": 6}
    obtenu = {t: valeur(su, f"SELECT count(*) FROM ref.{t}") for t in attendu}
    constat(obtenu)
    assert obtenu == attendu
