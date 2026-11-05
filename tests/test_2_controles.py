"""T-CTR : les contrôles trouvent des erreurs posées exprès. Tout se passe dans une transaction annulée."""
import pytest
from conftest import RACINE, connecter, valeur


@pytest.fixture(scope="module")
def passe():
    """Pose les erreurs, rejoue sql/31_controles.sql sans ses bornes de transaction, puis annule le tout."""
    conn = connecter()
    objets = {}
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.reprise = 'on'")

        # POS_02 et POS_04 : un support de Nantes déplacé de 100 km
        cur.execute("""UPDATE metier.support SET geom = ST_Translate(geom, 100000, 0)
                       WHERE id = (SELECT min(id) FROM metier.support s WHERE armoire_id IS NOT NULL AND insee = '44143'
                                   AND gestionnaire_id = (SELECT id FROM metier.gestionnaire WHERE code = 'NANTES')) RETURNING code""")
        objets["POS_02"] = objets["POS_04"] = cur.fetchone()[0]

        # POS_03 : deux supports au même endroit
        cur.execute("""WITH deux AS (SELECT id, code, geom, row_number() OVER (ORDER BY id) r FROM metier.support
                                     WHERE insee = '44020' ORDER BY id LIMIT 2)
                       UPDATE metier.support s SET geom = (SELECT geom FROM deux WHERE r = 1)
                       FROM deux d WHERE d.r = 2 AND s.id = d.id""")
        cur.execute("SELECT code FROM metier.support WHERE insee = '44020' ORDER BY id LIMIT 1")
        objets["POS_03"] = cur.fetchone()[0]

        # COH_05 : une armoire dont un support change de commune
        cur.execute("""UPDATE metier.support SET insee = '44215'
                       WHERE id = (SELECT min(id) FROM metier.support s WHERE s.insee = '44114' AND s.armoire_id IS NOT NULL)
                       RETURNING (SELECT code FROM metier.armoire a WHERE a.id = metier.support.armoire_id)""")
        objets["COH_05"] = cur.fetchone()[0]

        # TEM_03 : date de pose postérieure à la collecte
        cur.execute("""UPDATE metier.support SET date_pose = DATE '2030-06-01'
                       WHERE id = (SELECT min(id) FROM metier.support WHERE insee = '44162') RETURNING code""")
        objets["TEM_03"] = cur.fetchone()[0]

        # VAL_06 : LED déclarée à 9 000 K
        cur.execute("""UPDATE metier.point_lumineux SET temperature_couleur = 9000
                       WHERE id = (SELECT min(id) FROM metier.point_lumineux WHERE insee = '44143' AND type_source = 'LED') RETURNING code""")
        objets["VAL_06"] = cur.fetchone()[0]

        # REP_01 : un point qui disparaît de la base sans motif
        cur.execute("""UPDATE metier.point_lumineux SET retire_le = current_date
                       WHERE id = (SELECT max(id) FROM metier.point_lumineux WHERE insee = '44020')""")
        objets["REP_01"] = "NANTES"

        # COH_01 : une valeur que les correspondances ne connaissent pas, dans la source brute
        cur.execute("""UPDATE src.sde18 SET typ_sup = 'VALEUR_INCONNUE'
                       WHERE ctid = (SELECT ctid FROM src.sde18 WHERE typ_sup <> '' LIMIT 1)""")
        objets["COH_01"] = "typ_sup"

        # Décision déjà prise : elle doit survivre à la nouvelle passe
        cur.execute("""UPDATE controle.ecart SET decision = 'faux_positif', commentaire = 'Essai de la recette'
                       WHERE id = (SELECT min(id) FROM controle.ecart WHERE regle = 'VAL_02') RETURNING code_objet""")
        objets["decision"] = cur.fetchone()[0]

        texte = (RACINE / "sql" / "31_controles.sql").read_text(encoding="utf-8")
        cur.execute(texte.replace("BEGIN;", "", 1).replace("COMMIT;", ""))
    yield conn, objets
    conn.rollback()
    conn.close()


@pytest.mark.parametrize("regle", ["POS_02", "POS_03", "POS_04", "COH_05", "TEM_03", "VAL_06"])
def test_erreur_posee_trouvee(passe, constat, regle):
    """T-CTR-01 : une erreur posée sur un objet précis est retrouvée par la règle, sur cet objet"""
    conn, objets = passe
    n = valeur(conn, "SELECT count(*) FROM controle.ecart WHERE regle = %s AND code_objet = %s", regle, objets[regle])
    constat(f"{regle} relève {objets[regle]}")
    assert n >= 1


def test_point_disparu(passe, constat):
    """T-CTR-02 : un point retiré sans motif casse le bilan et le signale en bloquant"""
    conn, _ = passe
    n = valeur(conn, """SELECT mesure FROM controle.ecart e JOIN metier.gestionnaire g ON g.id = e.gestionnaire_id
                        WHERE e.regle = 'REP_01' AND g.code = 'NANTES'""")
    constat(f"REP_01 mesure un écart de {n}")
    assert n is not None and abs(n) == 1


def test_valeur_inconnue(passe, constat):
    """T-CTR-03 : une valeur source absente des correspondances ressort, au lieu d'être perdue"""
    conn, _ = passe
    n = valeur(conn, "SELECT count(*) FROM controle.ecart WHERE regle = 'COH_01' AND valeur_lue = 'VALEUR_INCONNUE'")
    constat(f"{n} écart COH_01 sur VALEUR_INCONNUE")
    assert n == 1


def test_decision_conservee(passe, constat):
    """T-CTR-04 : une décision déjà prise sur un écart survit à une nouvelle passe de contrôle"""
    conn, objets = passe
    decision = valeur(conn, "SELECT decision FROM controle.ecart WHERE regle = 'VAL_02' AND code_objet = %s", objets["decision"])
    constat(f"décision relue : {decision}")
    assert decision == "faux_positif"


def test_publication_hors_territoire(passe, constat):
    """T-CTR-05 : la publication titrée Loire, située en Haute-Savoie, est bloquée par POS_05"""
    conn, _ = passe  # même connexion : la passe garde un verrou sur controle.ecart jusqu'à son annulation
    code, mesure, trouve = valeur(conn, """SELECT ARRAY[code_objet, mesure::text, valeur_retenue] FROM controle.ecart WHERE regle = 'POS_05'""")
    constat(f"{code} : {mesure} supports, {trouve}")
    assert code == "LOIRE" and "74" in trouve
    assert valeur(conn, "SELECT count(*) FROM controle.ecart WHERE regle = 'POS_05'") == 1
    assert valeur(conn, "SELECT gravite FROM controle.regle WHERE code = 'POS_05'") == "bloquante"
