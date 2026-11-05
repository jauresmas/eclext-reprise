-- Rapprochement entre deux bases réelles qui décrivent les mêmes objets :
-- la communauté de communes Cœur de France et le syndicat d'énergie du Cher. Elles partagent la même
-- codification (AA-0001 dans une commune). Le rapprochement se fait sur la commune et le code ;
-- ce qui reste est cherché par la position, pour distinguer un objet absent d'un objet recodé.

BEGIN;

TRUNCATE controle.rapprochement;
DELETE FROM controle.ecart WHERE regle LIKE 'RAP_%';

CREATE TEMP TABLE t_ccf ON COMMIT DROP AS
SELECT m.insee, c.commune, c.code_point_lumineux AS code, nullif(trim(c.rue), '') AS rue,
       ST_Transform(ST_SetSRID(ST_MakePoint(nullif(c.x, '')::float8, nullif(c.y, '')::float8), 4326), 2154)::geometry(Point, 2154) AS geom
FROM src.ccf c
JOIN flux.lot l ON l.id = c.lot_id AND l.courant
JOIN ref.commune m ON ref.normaliser(m.nom) = ref.normaliser(c.commune) AND m.departement = '18';

CREATE TEMP TABLE t_syndicat ON COMMIT DROP AS
SELECT s.id, s.code, s.insee, s.proprietaire, s.geom, split_part(s.code, '-', 2) || substr(s.code, length(split_part(s.code, '-', 1)) + length(split_part(s.code, '-', 2)) + 2) AS code_source
FROM metier.support s
WHERE s.gestionnaire_id = (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18') AND s.retire_le IS NULL
  AND s.insee IN (SELECT DISTINCT insee FROM t_ccf);
CREATE INDEX ON t_syndicat USING gist (geom);
CREATE INDEX ON t_syndicat (insee, code_source);

-- Appariés sur la commune et le code
INSERT INTO controle.rapprochement (insee, commune, code, statut, distance_m, code_syndicat, client_syndicat, rue, geom_ccf, geom_syndicat)
SELECT c.insee, c.commune, c.code, 'apparie', round(ST_Distance(c.geom, s.geom)::numeric, 3), s.code, s.proprietaire, c.rue, c.geom, s.geom
FROM t_ccf c JOIN t_syndicat s ON s.insee = c.insee AND s.code_source = c.code;

-- Reste de Cœur de France : un support non apparié à moins de 5 m est un recodage probable
INSERT INTO controle.rapprochement (insee, commune, code, statut, distance_m, code_syndicat, client_syndicat, rue, geom_ccf, geom_syndicat)
SELECT c.insee, c.commune, c.code, CASE WHEN p.id IS NOT NULL THEN 'recode_probable' ELSE 'absent_syndicat' END,
       round(p.distance::numeric, 3), p.code, p.proprietaire, c.rue, c.geom, p.geom
FROM t_ccf c
LEFT JOIN LATERAL (
    SELECT s.id, s.code, s.proprietaire, s.geom, ST_Distance(c.geom, s.geom) AS distance
    FROM t_syndicat s
    WHERE ST_DWithin(c.geom, s.geom, 5)
      AND NOT EXISTS (SELECT 1 FROM controle.rapprochement r WHERE r.code_syndicat = s.code)
    ORDER BY c.geom <-> s.geom LIMIT 1
) p ON true
WHERE NOT EXISTS (SELECT 1 FROM t_syndicat s WHERE s.insee = c.insee AND s.code_source = c.code);

-- Reste du syndicat : objets intercommunaux que Cœur de France ne publie pas
INSERT INTO controle.rapprochement (insee, commune, code, statut, code_syndicat, client_syndicat, geom_syndicat)
SELECT s.insee, (SELECT nom FROM ref.commune m WHERE m.insee = s.insee), s.code_source, 'absent_ccf', s.code, s.proprietaire, s.geom
FROM t_syndicat s
WHERE s.proprietaire = 'EPCI'
  AND NOT EXISTS (SELECT 1 FROM controle.rapprochement r WHERE r.code_syndicat = s.code);

-- Écarts
INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, code_objet, insee, valeur_lue, geom)
SELECT 'RAP_01', (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18'), 'controle.rapprochement', r.commune || ' ' || r.code, r.insee, r.rue, r.geom_ccf
FROM controle.rapprochement r WHERE r.statut = 'absent_syndicat';

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'RAP_02', s.gestionnaire_id, 'metier.support', s.id, s.code, r.insee, r.client_syndicat, s.geom
FROM controle.rapprochement r JOIN metier.support s ON s.code = r.code_syndicat AND s.gestionnaire_id = (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18')
WHERE r.statut = 'absent_ccf';

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, code_objet, insee, valeur_lue, valeur_retenue, mesure, geom)
SELECT 'RAP_03', (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18'), 'controle.rapprochement', r.code_syndicat, r.insee, r.code, r.code_syndicat, r.distance_m, r.geom_syndicat
FROM controle.rapprochement r WHERE r.statut = 'recode_probable';

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, mesure, geom)
SELECT 'RAP_04', s.gestionnaire_id, 'metier.support', s.id, s.code, r.insee, r.distance_m, s.geom
FROM controle.rapprochement r JOIN metier.support s ON s.code = r.code_syndicat AND s.gestionnaire_id = (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18')
WHERE r.statut = 'apparie' AND r.distance_m > 5;

INSERT INTO controle.ecart (regle, gestionnaire_id, table_objet, objet_id, code_objet, insee, valeur_lue, geom)
SELECT 'RAP_05', s.gestionnaire_id, 'metier.support', s.id, s.code, r.insee, coalesce(r.client_syndicat, 'non renseigné'), s.geom
FROM controle.rapprochement r JOIN metier.support s ON s.code = r.code_syndicat AND s.gestionnaire_id = (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18')
WHERE r.statut = 'apparie' AND r.client_syndicat IS DISTINCT FROM 'EPCI';

COMMIT;
