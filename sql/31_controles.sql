-- Contrôles de la reprise. Chaque règle relit la source brute ou la base et écrit ses écarts.
-- Les décisions déjà prises (confirmée, faux positif, corrigée) survivent à une nouvelle passe.

BEGIN;

CREATE TEMP TABLE t_decisions ON COMMIT DROP AS
SELECT regle, gestionnaire_id, code_objet, decision, commentaire, traite_par, traite_le
FROM controle.ecart WHERE decision <> 'a_traiter';
TRUNCATE controle.ecart RESTART IDENTITY;

CREATE TEMP TABLE t_gest ON COMMIT DROP AS SELECT code, id FROM metier.gestionnaire;
CREATE TEMP TABLE t_lots ON COMMIT DROP AS SELECT source, id AS lot_id, to_date(date_collecte, 'YYYYMMDD') AS date_collecte FROM flux.lot WHERE courant;

-- 1. Reprise : ce qui est entré se retrouve à la sortie ------------------------------------------

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue, valeur_retenue, mesure)
SELECT 'REP_01', g.id, b.gestionnaire,
       b.lignes_source::text, (b.points_repris + b.lignes_fusionnees + b.lignes_ecartees)::text, b.ecart
FROM controle.bilan_reprise b JOIN t_gest g ON g.code = b.gestionnaire
WHERE b.ecart <> 0;

-- Puissances par armoire : lecture directe du fichier, sans passer par les conversions de la reprise
INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
WITH s AS (
    SELECT n.identifiant_de_l_armoire AS armoire, sum(greatest(ref.vers_nombre(n.puissance_du_foyer_w), 0)) AS puissance
    FROM src.nantes n JOIN t_lots l ON l.lot_id = n.lot_id GROUP BY 1
), c AS (
    SELECT a.id, a.code, a.insee, a.geom, sum(coalesce(p.puissance_w, 0)) AS puissance
    FROM metier.armoire a JOIN metier.support u ON u.armoire_id = a.id
    JOIN metier.point_lumineux p ON p.support_id = u.id AND p.retire_le IS NULL
    WHERE a.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
    GROUP BY a.id, a.code, a.insee, a.geom
)
SELECT 'REP_02', (SELECT id FROM t_gest WHERE code = 'NANTES'), 'metier.armoire', c.id, coalesce(c.code, s.armoire), c.insee,
       s.puissance::text, c.puissance::text, abs(coalesce(s.puissance, 0) - coalesce(c.puissance, 0)), c.geom
FROM s FULL JOIN c ON c.code = s.armoire
WHERE abs(coalesce(s.puissance, 0) - coalesce(c.puissance, 0)) > 0.05;

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, insee, valeur_lue, valeur_retenue, mesure)
WITH s AS (
    SELECT s.insee, count(*) AS n FROM src.sde18 s JOIN t_lots l ON l.lot_id = s.lot_id GROUP BY 1
), c AS (
    SELECT p.insee, count(*) AS n FROM metier.point_lumineux p
    WHERE p.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18') AND p.retire_le IS NULL GROUP BY 1
)
SELECT 'REP_03', (SELECT id FROM t_gest WHERE code = 'SDE18'), coalesce(s.insee, c.insee), coalesce(s.insee, c.insee),
       s.n::text, c.n::text, abs(coalesce(s.n, 0) - coalesce(c.n, 0))
FROM s FULL JOIN c ON c.insee = s.insee
WHERE coalesce(s.n, 0) <> coalesce(c.n, 0);

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, mesure, geom)
SELECT 'REP_04', p.gestionnaire_id, 'metier.point_lumineux', p.id, p.code, p.insee,
       ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(split_part(n.geolocalisation, ',', 2)::float8, split_part(n.geolocalisation, ',', 1)::float8), 4326), 2154), p.geom),
       p.geom
FROM metier.point_lumineux p
JOIN src.nantes n ON n.ligne = p.ligne_source
JOIN t_lots l ON l.lot_id = n.lot_id AND l.source = 'nantes'
WHERE p.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
  AND NOT ST_DWithin(ST_Transform(ST_SetSRID(ST_MakePoint(split_part(n.geolocalisation, ',', 2)::float8, split_part(n.geolocalisation, ',', 1)::float8), 4326), 2154), p.geom, 0.01);

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, mesure, geom)
SELECT 'REP_04', p.gestionnaire_id, 'metier.point_lumineux', p.id, p.code, p.insee,
       ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(s.lon::float8, s.lat::float8), 4326), 2154), p.geom), p.geom
FROM metier.point_lumineux p
JOIN src.sde18 s ON s.ligne = p.ligne_source
JOIN t_lots l ON l.lot_id = s.lot_id AND l.source = 'sde18'
WHERE p.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18')
  AND NOT ST_DWithin(ST_Transform(ST_SetSRID(ST_MakePoint(s.lon::float8, s.lat::float8), 4326), 2154), p.geom, 0.01);

-- 2. Exhaustivité ------------------------------------------------------------------------------

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, code_objet, insee, valeur_lue)
SELECT 'EXH_01', (SELECT id FROM t_gest WHERE code = 'SDE18'), 'ref.commune', c.insee, c.insee, c.nom
FROM ref.commune c
WHERE c.departement = '18'
  AND NOT EXISTS (SELECT 1 FROM metier.support s WHERE s.insee = c.insee AND s.retire_le IS NULL
                    AND s.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18'));

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, code_objet, insee, valeur_lue)
SELECT 'EXH_01', (SELECT id FROM t_gest WHERE code = 'NANTES'), 'ref.commune', c.insee, c.insee, c.nom
FROM ref.commune c
WHERE c.epci = '244400404'
  AND NOT EXISTS (SELECT 1 FROM metier.support s WHERE s.insee = c.insee AND s.retire_le IS NULL
                    AND s.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES'));

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue, mesure)
SELECT 'EXH_02', g.id, c.attribut, c.origine, c.points
FROM controle.conformite_attribut c JOIN t_gest g ON g.code = c.gestionnaire
WHERE c.obligatoire AND c.renseignes = 0;

-- 3. Cohérence logique -------------------------------------------------------------------------

-- Toute valeur non prévue ressort ici : c'est ce qui garde les correspondances à jour
INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue, valeur_retenue, mesure)
SELECT 'COH_01', (SELECT id FROM t_gest WHERE code = 'SDE18'), v.champ, v.valeur, 'non converti', count(*)
FROM src.sde18 s JOIN t_lots l ON l.lot_id = s.lot_id
CROSS JOIN LATERAL (VALUES ('typ_sup', s.typ_sup), ('etat', s.etat), ('type_pose', s.type_pose), ('type_massif', s.type_massif),
                           ('client', s.client), ('prise_guirlande_illumination', s.prise_guirlande_illumination)) AS v(champ, valeur)
WHERE nullif(v.valeur, '') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ref.correspondance c WHERE c.source = 'sde18' AND c.champ_source = v.champ AND c.valeur_source = v.valeur)
GROUP BY v.champ, v.valeur;

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue, valeur_retenue, mesure)
SELECT 'COH_01', (SELECT id FROM t_gest WHERE code = 'NANTES'), v.champ, v.valeur, 'non converti', count(*)
FROM src.nantes s JOIN t_lots l ON l.lot_id = s.lot_id
CROSS JOIN LATERAL (VALUES ('type_de_lampe', s.type_de_lampe), ('statut', s.statut), ('nature_du_support', s.nature_du_support)) AS v(champ, valeur)
WHERE nullif(v.valeur, '') IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM ref.correspondance c WHERE c.source = 'nantes' AND c.champ_source = v.champ AND c.valeur_source = v.valeur)
GROUP BY v.champ, v.valeur;

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue, valeur_retenue, mesure)
SELECT 'COH_01', (SELECT id FROM t_gest WHERE code = 'LOIRE'), v.champ, v.valeur, 'XX', count(*)
FROM src.loire s JOIN t_lots l ON l.lot_id = s.lot_id
CROSS JOIN LATERAL (VALUES
    ('usage', s.usage, (SELECT array_agg(code::text) FROM ref.usage)),
    ('typeSource', s.typesource, (SELECT array_agg(code::text) FROM ref.type_source)),
    ('structure', s.structure, (SELECT array_agg(code::text) FROM ref.structure_luminaire)),
    ('support', s.support, (SELECT array_agg(code::text) FROM ref.support_luminaire))) AS v(champ, valeur, liste)
WHERE s.id <> '' AND nullif(v.valeur, '') IS NOT NULL AND NOT (v.valeur = ANY(v.liste))
GROUP BY v.champ, v.valeur;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, geom)
SELECT 'COH_02', p.gestionnaire_id, 'metier.point_lumineux', p.id, p.code, p.insee, n.identifiant_du_foyer, p.code, p.geom
FROM src.nantes n
JOIN t_lots l ON l.lot_id = n.lot_id
JOIN metier.point_lumineux p ON p.ligne_source = n.ligne AND p.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE n.identifiant_du_foyer IN (SELECT identifiant_du_foyer FROM src.nantes m JOIN t_lots k ON k.lot_id = m.lot_id
                                 GROUP BY 1 HAVING count(*) > 1);

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'COH_03', s.gestionnaire_id, 'metier.support', s.id, s.code, s.insee, split_part(s.code, '-', 2) || coalesce('-' || nullif(split_part(s.code, '-', 3), ''), ''), s.geom
FROM metier.support s
WHERE s.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18')
  AND s.code !~ '^[0-9AB]{5}-[A-Z0-9]+-[0-9]+$' AND s.retire_le IS NULL;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, mesure, geom)
SELECT 'COH_04', s.gestionnaire_id, 'metier.support', s.id, s.code, s.insee, count(DISTINCT p.depart_id), s.geom
FROM metier.support s JOIN metier.point_lumineux p ON p.support_id = s.id
WHERE p.depart_id IS NOT NULL
GROUP BY s.id HAVING count(DISTINCT p.depart_id) > 1;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, mesure, geom)
SELECT 'COH_05', a.gestionnaire_id, 'metier.armoire', a.id, a.code, a.insee, string_agg(DISTINCT s.insee, ', '), count(DISTINCT s.insee), a.geom
FROM metier.armoire a JOIN metier.support s ON s.armoire_id = a.id
GROUP BY a.id HAVING count(DISTINCT s.insee) > 1;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'COH_06', u.gestionnaire_id, 'metier.support', u.id, u.code, u.insee,
       'voies : ' || t.voies || ', hauteurs : ' || t.hauteurs, u.geom
FROM (SELECT n.identifiant_du_support AS code, count(DISTINCT n.nom_de_la_voie) AS voies, count(DISTINCT n.hauteur_du_support) AS hauteurs
      FROM src.nantes n JOIN t_lots l ON l.lot_id = n.lot_id
      WHERE n.ligne_doublon = '1'
      GROUP BY 1 HAVING count(DISTINCT n.nom_de_la_voie) > 1 OR count(DISTINCT n.hauteur_du_support) > 1) t
JOIN metier.support u ON u.code = t.code AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES');

-- Lignes coupées : COH_07 si le début de ligne a été retrouvé, COH_08 sinon
INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT CASE WHEN r.ligne IS NOT NULL THEN 'COH_07' ELSE 'COH_08' END,
       p.gestionnaire_id, 'metier.point_lumineux', p.id, p.code, p.insee, 'ligne ' || p.ligne_source, p.geom
FROM metier.point_lumineux p
JOIN src.loire s ON s.ligne = p.ligne_source
JOIN t_lots l ON l.lot_id = s.lot_id AND l.source = 'loire'
LEFT JOIN controle.rejet r ON r.lot_id = l.lot_id AND r.ligne = p.ligne_source - 1 AND r.motif LIKE 'fusionnee%'
WHERE p.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'LOIRE') AND s.id = '';

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue)
SELECT 'COH_09', (SELECT id FROM t_gest WHERE code = 'LOIRE'), 'ligne ' || r.ligne, left(r.contenu::text, 200)
FROM controle.rejet r JOIN t_lots l ON l.lot_id = r.lot_id AND l.source = 'loire'
WHERE r.motif NOT LIKE 'fusionnee%';

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, geom)
SELECT 'COH_10', p.gestionnaire_id, 'metier.point_lumineux', p.id, p.code, p.insee, n.designation_de_la_lampe, n.type_de_lampe, p.geom
FROM src.nantes n
JOIN t_lots l ON l.lot_id = n.lot_id
JOIN metier.point_lumineux p ON p.ligne_source = n.ligne AND p.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE n.type_de_lampe <> '' AND split_part(n.designation_de_la_lampe, ' ', 1) NOT IN ('', '-')
  AND left(split_part(n.designation_de_la_lampe, ' ', 1), 2) <> left(n.type_de_lampe, 2);

-- 4. Précision de position ---------------------------------------------------------------------

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, mesure, geom)
SELECT CASE WHEN d.distance > 500 THEN 'POS_02' ELSE 'POS_01' END, s.gestionnaire_id, 'metier.support', s.id, s.code, s.insee, c.nom, round(d.distance::numeric, 1), s.geom
FROM metier.support s
JOIN ref.commune c ON c.insee = s.insee
CROSS JOIN LATERAL (SELECT ST_Distance(s.geom, c.geom) AS distance) d
WHERE s.retire_le IS NULL AND NOT ST_DWithin(s.geom, c.geom, 50)
  AND s.gestionnaire_id <> (SELECT id FROM t_gest WHERE code = 'LOIRE');  -- commune déduite de la position

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, mesure, geom)
SELECT 'POS_03', a.gestionnaire_id, 'metier.support', a.id, a.code, a.insee, b.code, round(ST_Distance(a.geom, b.geom)::numeric, 3), a.geom
FROM metier.support a
JOIN metier.support b ON a.gestionnaire_id = b.gestionnaire_id AND a.id < b.id AND ST_DWithin(a.geom, b.geom, 0.5)
WHERE a.retire_le IS NULL AND b.retire_le IS NULL;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, mesure, geom)
SELECT 'POS_04', s.gestionnaire_id, 'metier.support', s.id, s.code, s.insee, a.code, round(ST_Distance(s.geom, a.geom)::numeric, 0), s.geom
FROM metier.support s JOIN metier.armoire a ON a.id = s.armoire_id
WHERE s.retire_le IS NULL AND NOT ST_DWithin(s.geom, a.geom, 2000);

INSERT INTO controle.ecart (regle, gestionnaire_id, code_objet, valeur_lue, valeur_retenue, mesure)
SELECT 'POS_05', g.id, g.code, 'département annoncé : ' || g.territoire_annonce,
       'départements trouvés : ' || string_agg(DISTINCT c.departement, ', '), count(*)
FROM metier.support s JOIN metier.gestionnaire g ON g.id = s.gestionnaire_id JOIN ref.commune c ON c.insee = s.insee
WHERE s.retire_le IS NULL
GROUP BY g.id, g.code, g.territoire_annonce
HAVING count(*) FILTER (WHERE c.departement = g.territoire_annonce) < 0.5 * count(*);

-- 5. Exactitude thématique ---------------------------------------------------------------------

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'VAL_01', u.gestionnaire_id, 'metier.support', u.id, u.code, u.insee, s.hauteur, u.geom
FROM src.sde18 s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.support u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18')
WHERE ref.vers_nombre(s.hauteur) = 0;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'VAL_01', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.hauteur_du_support, u.geom
FROM src.nantes s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE ref.vers_nombre(s.hauteur_du_support) = 0;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'VAL_02', u.gestionnaire_id, 'metier.support', u.id, u.code, u.insee, s.hauteur, u.hauteur_m::text, ref.vers_nombre(s.hauteur), u.geom
FROM src.sde18 s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.support u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18')
WHERE ref.vers_nombre(s.hauteur) > 30;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'VAL_02', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.hauteur_du_support, u.hauteur_feu_m::text, ref.vers_nombre(s.hauteur_du_support), u.geom
FROM src.nantes s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE ref.vers_nombre(s.hauteur_du_support) > 30;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'VAL_03', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.puissance_du_foyer_w, u.puissance_w::text, ref.vers_nombre(s.puissance_du_foyer_w), u.geom
FROM src.nantes s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE ref.vers_nombre(s.puissance_du_foyer_w) = 0 OR ref.vers_nombre(s.puissance_du_foyer_w) > 1000;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'VAL_03', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.puissance, u.puissance_w::text, ref.vers_nombre(s.puissance), u.geom
FROM src.loire s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'LOIRE')
WHERE s.id <> '' AND (ref.vers_nombre(s.puissance) = 0 OR ref.vers_nombre(s.puissance) > 1000);

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'VAL_04', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.temperaturecouleur, u.geom
FROM src.loire s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'LOIRE')
WHERE s.id <> '' AND s.temperaturecouleur <> ''
  AND NOT coalesce(ref.vers_nombre(s.temperaturecouleur) BETWEEN 1000 AND 10000, false);

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, mesure, geom)
SELECT 'VAL_05', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.saillie_m, ref.vers_nombre(s.saillie_m), u.geom
FROM src.nantes s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE ref.vers_nombre(s.saillie_m) > 20;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'VAL_06', p.gestionnaire_id, 'metier.point_lumineux', p.id, p.code, p.insee, p.type_source, p.temperature_couleur::text, p.temperature_couleur, p.geom
FROM metier.point_lumineux p
WHERE p.retire_le IS NULL
  AND ((p.type_source IN ('SHP', 'SBP') AND p.temperature_couleur NOT BETWEEN 1800 AND 2400)
    OR (p.type_source = 'LED' AND p.temperature_couleur NOT BETWEEN 1800 AND 6500));

-- La puissance du foyer comprend l'appareillage : environ 1,05 à 1,10 fois celle de la lampe, par lampe
INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'VAL_07', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.designation_de_la_lampe || ' x ' || s.nombre_de_lampes,
       s.puissance_du_foyer_w,
       round(ref.vers_nombre(s.puissance_du_foyer_w) / (ref.vers_nombre(split_part(s.designation_de_la_lampe, ' ', 3)) * s.nombre_de_lampes::numeric), 2), u.geom
FROM src.nantes s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'NANTES')
WHERE ref.vers_nombre(split_part(s.designation_de_la_lampe, ' ', 3)) > 0 AND ref.vers_nombre(s.puissance_du_foyer_w) > 0
  AND ref.vers_nombre(s.puissance_du_foyer_w) / (ref.vers_nombre(split_part(s.designation_de_la_lampe, ' ', 3)) * s.nombre_de_lampes::numeric) NOT BETWEEN 0.5 AND 2;

-- 6. Qualité temporelle ------------------------------------------------------------------------

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'TEM_01', u.gestionnaire_id, 'metier.support', u.id, u.code, u.insee, s.date_pose, u.geom
FROM src.sde18 s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.support u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'SDE18')
WHERE s.date_pose = '19700101';

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'TEM_02', u.gestionnaire_id, 'metier.point_lumineux', u.id, u.code, u.insee, s.datepremieinstallation, u.geom
FROM src.loire s JOIN t_lots l ON l.lot_id = s.lot_id
JOIN metier.point_lumineux u ON u.ligne_source = s.ligne AND u.gestionnaire_id = (SELECT id FROM t_gest WHERE code = 'LOIRE')
WHERE s.id <> '' AND s.datepremieinstallation <> ''
  AND NOT coalesce(ref.vers_date(s.datepremieinstallation) >= DATE '1900-01-01', false);

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'TEM_03', u.gestionnaire_id, 'metier.support', u.id, u.code, u.insee, u.date_pose::text, u.geom
FROM metier.support u JOIN t_lots l ON l.lot_id = u.lot_id
WHERE u.date_pose > l.date_collecte;

-- Décisions déjà prises
UPDATE controle.ecart e
SET decision = d.decision, commentaire = d.commentaire, traite_par = d.traite_par, traite_le = d.traite_le
FROM t_decisions d
WHERE d.regle = e.regle AND d.gestionnaire_id IS NOT DISTINCT FROM e.gestionnaire_id AND d.code_objet IS NOT DISTINCT FROM e.code_objet;

COMMIT;
ANALYZE controle.ecart;
