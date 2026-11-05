-- Reprise des supports du syndicat d'énergie du Cher.
--
-- La source décrit des supports, pas des luminaires. Le géostandard demande des points lumineux :
-- un point est créé par support, marqué un_point_par_support, sans préjuger du nombre réel.
-- Le script est relançable : une ligne déjà reprise et inchangée n'est pas réécrite.

BEGIN;
SET LOCAL app.reprise = 'on';

CREATE TEMP TABLE t_lot ON COMMIT DROP AS
    SELECT id AS lot_id, to_date(date_collecte, 'YYYYMMDD') AS date_collecte FROM flux.lot WHERE source = 'sde18' AND courant;
CREATE TEMP TABLE t_gest ON COMMIT DROP AS SELECT id FROM metier.gestionnaire WHERE code = 'SDE18';

CREATE TEMP TABLE t_sde18 ON COMMIT DROP AS
SELECT s.lot_id,
       s.ligne,
       s.code_support AS code,
       s.insee,
       substring(s.code_support FROM '^[A-Za-z0-9.]+') AS armoire_source,
       s.insee || '-' || substring(s.code_support FROM '^[A-Za-z0-9.]+') AS armoire_code,
       coalesce(sup.valeur_cible, 'XX') AS type_support,
       coalesce(stru.valeur_cible, 'XX') AS structure,
       CASE WHEN ref.vers_nombre(s.hauteur) > 0 AND ref.vers_nombre(s.hauteur) <= 60 THEN ref.vers_nombre(s.hauteur) END AS hauteur_m,
       nullif(trim(s.marque_support), '') AS marque,
       nullif(trim(s.couleur_ral), '') AS couleur,
       et.valeur_cible AS etat,
       pos.valeur_cible AS type_pose,
       mas.valeur_cible AS type_massif,
       dim.valeur_cible AS dimension_massif,
       nullif(nullif(lower(regexp_replace(s.entraxe, '\s*[xX*]\s*', 'x', 'g')), ''), '0') AS entraxe,
       ref.vers_booleen(s.presence_terre) AS presence_terre,
       pri.valeur_cible::boolean AS prise_illumination,
       ref.vers_booleen(s.autonome) AS autonome,
       CASE WHEN s.date_pose <> '19700101' THEN ref.vers_date(s.date_pose) END AS date_pose,
       pro.valeur_cible AS proprietaire,
       pub.valeur_cible::boolean AS eclairage_public,
       ref.vers_booleen(s.transfert_sde) AS competence_transferee,
       nullif(trim(s.type_maintenance), '') AS type_maintenance,
       nullif(trim(s.clas_prec), '') AS classe_precision,
       nullif(trim(s.observation), '') AS observation,
       ST_Transform(ST_SetSRID(ST_MakePoint(s.lon::float8, s.lat::float8), 4326), 2154)::geometry(Point, 2154) AS geom
FROM src.sde18 s
JOIN t_lot l ON l.lot_id = s.lot_id
LEFT JOIN ref.correspondance sup  ON sup.source = 'sde18' AND sup.champ_source = 'typ_sup' AND sup.attribut_cible = 'type_support' AND sup.valeur_source = coalesce(s.typ_sup, '')
LEFT JOIN ref.correspondance stru ON stru.source = 'sde18' AND stru.champ_source = 'typ_sup' AND stru.attribut_cible = 'structure' AND stru.valeur_source = s.typ_sup
LEFT JOIN ref.correspondance et   ON et.source = 'sde18' AND et.champ_source = 'etat' AND et.valeur_source = s.etat
LEFT JOIN ref.correspondance pos  ON pos.source = 'sde18' AND pos.champ_source = 'type_pose' AND pos.valeur_source = s.type_pose
LEFT JOIN ref.correspondance mas  ON mas.source = 'sde18' AND mas.champ_source = 'type_massif' AND mas.attribut_cible = 'type_massif' AND mas.valeur_source = s.type_massif
LEFT JOIN ref.correspondance dim  ON dim.source = 'sde18' AND dim.champ_source = 'type_massif' AND dim.attribut_cible = 'dimension_massif' AND dim.valeur_source = s.type_massif
LEFT JOIN ref.correspondance pri  ON pri.source = 'sde18' AND pri.champ_source = 'prise_guirlande_illumination' AND pri.valeur_source = s.prise_guirlande_illumination
LEFT JOIN ref.correspondance pro  ON pro.source = 'sde18' AND pro.champ_source = 'client' AND pro.attribut_cible = 'proprietaire' AND pro.valeur_source = s.client
LEFT JOIN ref.correspondance pub  ON pub.source = 'sde18' AND pub.champ_source = 'client' AND pub.attribut_cible = 'eclairage_public' AND pub.valeur_source = s.client;

ANALYZE t_sde18;

-- Armoires : le préfixe du code support (AA dans AA-0001) ; il n'est unique que dans sa commune.
INSERT INTO metier.armoire (gestionnaire_id, code, code_source, insee, geom, lot_id)
SELECT (SELECT id FROM t_gest), armoire_code, min(armoire_source), min(insee),
       ST_Centroid(ST_Collect(geom))::geometry(Point, 2154), min(lot_id)
FROM t_sde18 GROUP BY armoire_code
ON CONFLICT (gestionnaire_id, code) DO UPDATE
    SET geom = EXCLUDED.geom, lot_id = EXCLUDED.lot_id, retire_le = NULL
    WHERE NOT metier.armoire.maj_locale
      AND (NOT ST_Equals(metier.armoire.geom, EXCLUDED.geom) OR metier.armoire.retire_le IS NOT NULL);

ANALYZE metier.armoire;

INSERT INTO metier.support (gestionnaire_id, code, insee, armoire_id, type_support, hauteur_m, couleur, marque, etat, type_pose,
                            type_massif, dimension_massif, entraxe, presence_terre, prise_illumination, autonome, date_pose,
                            proprietaire, competence_transferee, type_maintenance, classe_precision, observation, geom, lot_id, ligne_source)
SELECT (SELECT id FROM t_gest), t.insee || '-' || t.code, t.insee, a.id, t.type_support, t.hauteur_m, t.couleur, t.marque, t.etat, t.type_pose,
       t.type_massif, t.dimension_massif, t.entraxe, t.presence_terre, t.prise_illumination, t.autonome, t.date_pose,
       t.proprietaire, t.competence_transferee, t.type_maintenance, t.classe_precision, t.observation, t.geom, t.lot_id, t.ligne
FROM t_sde18 t
JOIN metier.armoire a ON a.gestionnaire_id = (SELECT id FROM t_gest) AND a.code = t.armoire_code
ON CONFLICT (gestionnaire_id, code) DO UPDATE SET
    armoire_id = EXCLUDED.armoire_id, type_support = EXCLUDED.type_support, hauteur_m = EXCLUDED.hauteur_m, couleur = EXCLUDED.couleur,
    marque = EXCLUDED.marque, etat = EXCLUDED.etat, type_pose = EXCLUDED.type_pose, type_massif = EXCLUDED.type_massif,
    dimension_massif = EXCLUDED.dimension_massif, entraxe = EXCLUDED.entraxe, presence_terre = EXCLUDED.presence_terre,
    prise_illumination = EXCLUDED.prise_illumination, autonome = EXCLUDED.autonome, date_pose = EXCLUDED.date_pose,
    proprietaire = EXCLUDED.proprietaire, competence_transferee = EXCLUDED.competence_transferee,
    type_maintenance = EXCLUDED.type_maintenance, classe_precision = EXCLUDED.classe_precision,
    observation = EXCLUDED.observation, geom = EXCLUDED.geom, lot_id = EXCLUDED.lot_id, ligne_source = EXCLUDED.ligne_source, retire_le = NULL
WHERE NOT metier.support.maj_locale
  AND ((metier.support.type_support, metier.support.hauteur_m, metier.support.etat, metier.support.date_pose, metier.support.proprietaire,
        metier.support.type_pose, metier.support.type_massif, metier.support.observation, metier.support.retire_le)
       IS DISTINCT FROM (EXCLUDED.type_support, EXCLUDED.hauteur_m, EXCLUDED.etat, EXCLUDED.date_pose, EXCLUDED.proprietaire,
                         EXCLUDED.type_pose, EXCLUDED.type_massif, EXCLUDED.observation, NULL::date)
       OR NOT ST_Equals(metier.support.geom, EXCLUDED.geom));

ANALYZE metier.support;

INSERT INTO metier.point_lumineux (gestionnaire_id, code, support_id, insee, statut, eclairage_public, usage, type_source, structure,
                                   valide_de, hauteur_feu_m, un_point_par_support, geom, lot_id, ligne_source)
SELECT s.gestionnaire_id, s.code, s.id, s.insee, 'functional', t.eclairage_public, 'XX', 'XX', t.structure,
       t.date_pose, t.hauteur_m, true, t.geom, t.lot_id, t.ligne
FROM t_sde18 t
JOIN metier.support s ON s.gestionnaire_id = (SELECT id FROM t_gest) AND s.code = t.insee || '-' || t.code
ON CONFLICT (gestionnaire_id, code) DO UPDATE SET
    eclairage_public = EXCLUDED.eclairage_public, structure = EXCLUDED.structure, valide_de = EXCLUDED.valide_de,
    hauteur_feu_m = EXCLUDED.hauteur_feu_m, geom = EXCLUDED.geom, lot_id = EXCLUDED.lot_id, ligne_source = EXCLUDED.ligne_source, retire_le = NULL
WHERE NOT metier.point_lumineux.maj_locale
  AND ((metier.point_lumineux.eclairage_public, metier.point_lumineux.structure, metier.point_lumineux.valide_de,
        metier.point_lumineux.hauteur_feu_m, metier.point_lumineux.retire_le)
       IS DISTINCT FROM (EXCLUDED.eclairage_public, EXCLUDED.structure, EXCLUDED.valide_de, EXCLUDED.hauteur_feu_m, NULL::date)
       OR NOT ST_Equals(metier.point_lumineux.geom, EXCLUDED.geom));

ANALYZE metier.point_lumineux;

-- Ce qui a disparu de la source est daté, jamais supprimé : il peut porter des interventions
UPDATE metier.point_lumineux p SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE p.gestionnaire_id = (SELECT id FROM t_gest) AND p.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_sde18 t WHERE t.insee || '-' || t.code = p.code);
UPDATE metier.support s SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE s.gestionnaire_id = (SELECT id FROM t_gest) AND s.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_sde18 t WHERE t.insee || '-' || t.code = s.code);
UPDATE metier.armoire a SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE a.gestionnaire_id = (SELECT id FROM t_gest) AND a.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_sde18 t WHERE t.armoire_code = a.code);

COMMIT;
