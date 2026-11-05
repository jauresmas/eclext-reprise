-- Reprise des luminaires de Nantes Métropole : la seule source qui publie toute la hiérarchie,
-- de l'armoire au foyer. Une ligne du fichier est un foyer, c'est-à-dire un point lumineux.
--
-- Quatre identifiants (EPBO036010 à 013) sont portés chacun par deux objets réellement différents :
-- positions distantes, hauteurs et puissances différentes. Les deux sont gardés, le second reçoit
-- le suffixe -D2 ; le contrôle COH_02 les signale au gestionnaire.

BEGIN;
SET LOCAL app.reprise = 'on';

CREATE TEMP TABLE t_lot ON COMMIT DROP AS
    SELECT id AS lot_id, to_date(date_collecte, 'YYYYMMDD') AS date_collecte FROM flux.lot WHERE source = 'nantes' AND courant;
CREATE TEMP TABLE t_gest ON COMMIT DROP AS SELECT id FROM metier.gestionnaire WHERE code = 'NANTES';

-- Noms de commune de la source vers le code INSEE
CREATE TEMP TABLE t_commune ON COMMIT DROP AS
SELECT DISTINCT n.nom_de_la_commune AS nom, c.insee
FROM src.nantes n JOIN t_lot l ON l.lot_id = n.lot_id
JOIN ref.commune c ON c.epci = '244400404' AND ref.normaliser(c.nom) = ref.normaliser(n.nom_de_la_commune);

-- Structure du luminaire : lue dans le nom du foyer quand il contient un mot explicite
CREATE TEMP TABLE t_structure ON COMMIT DROP AS
SELECT DISTINCT ON (f.type_de_foyer) f.type_de_foyer, c.valeur_cible AS structure
FROM (SELECT DISTINCT n.type_de_foyer FROM src.nantes n JOIN t_lot l ON l.lot_id = n.lot_id) f
JOIN ref.correspondance c ON c.source = 'nantes' AND c.champ_source = 'mot du type de foyer'
 AND upper(unaccent(f.type_de_foyer)) ~ ('\m' || c.valeur_source || '\M')
ORDER BY f.type_de_foyer, c.valeur_source;

CREATE TEMP TABLE t_nantes ON COMMIT DROP AS
SELECT n.lot_id,
       n.ligne,
       n.identifiant_du_foyer || CASE WHEN n.ligne_doublon <> '1' THEN '-D' || n.ligne_doublon ELSE '' END AS code_point,
       n.identifiant_du_support || CASE WHEN n.ligne_doublon <> '1' THEN '-D' || n.ligne_doublon ELSE '' END AS code_support,
       n.identifiant_de_l_armoire AS code_armoire,
       nullif(trim(n.identifiant_du_depart), '') AS depart,
       cm.insee AS insee_declare,
       nullif(trim(n.nom_de_la_voie), '') AS voie,
       nullif(trim(n.nom_du_quartier), '') AS quartier,
       coalesce(ts.valeur_cible, 'XX') AS type_source,
       coalesce(st.structure, 'XX') AS structure,
       coalesce(sup.valeur_cible, 'XX') AS type_support,
       pub.valeur_cible::boolean AS eclairage_public,
       CASE WHEN ref.vers_nombre(n.puissance_du_foyer_w) > 0 THEN ref.vers_nombre(n.puissance_du_foyer_w) END AS puissance_w,
       CASE WHEN ref.vers_nombre(n.hauteur_du_support) > 0 AND ref.vers_nombre(n.hauteur_du_support) <= 60 THEN ref.vers_nombre(n.hauteur_du_support) END AS hauteur_m,
       CASE WHEN ref.vers_nombre(n.saillie_m) BETWEEN 0 AND 20 THEN ref.vers_nombre(n.saillie_m) END AS saillie_m,
       nullif(trim(n.nature_du_support), '') AS nature,
       nullif(trim(n.forme_du_support), '') AS forme,
       nullif(trim(n.couleur_du_support), '') AS couleur,
       nullif(trim(n.secteur_de_maintenance), '') AS exploitant,
       nullif(trim(n.type_de_foyer), '') AS modele,
       nullif(trim(n.designation_de_la_lampe), '') AS designation,
       (substring(split_part(n.designation_de_la_lampe, ' ', 5) FROM '^[0-9]{4}$'))::integer AS temperature,
       (substring(n.designation_de_la_lampe FROM '([0-9]+)lm'))::numeric AS flux_source,
       coalesce(nullif(n.nombre_de_lampes, '')::smallint, 1) AS nb_sources,
       ST_Transform(ST_SetSRID(ST_MakePoint(split_part(n.geolocalisation, ',', 2)::float8,
                                            split_part(n.geolocalisation, ',', 1)::float8), 4326), 2154)::geometry(Point, 2154) AS geom
FROM src.nantes n
JOIN t_lot l ON l.lot_id = n.lot_id
LEFT JOIN t_commune cm ON cm.nom = n.nom_de_la_commune
LEFT JOIN t_structure st ON st.type_de_foyer = n.type_de_foyer
LEFT JOIN ref.correspondance ts  ON ts.source = 'nantes' AND ts.champ_source = 'type_de_lampe' AND ts.valeur_source = n.type_de_lampe
LEFT JOIN ref.correspondance sup ON sup.source = 'nantes' AND sup.champ_source = 'nature_du_support' AND sup.valeur_source = n.nature_du_support
LEFT JOIN ref.correspondance pub ON pub.source = 'nantes' AND pub.champ_source = 'statut' AND pub.valeur_source = n.statut;

-- Commune non renseignée : celle qui contient le point
UPDATE t_nantes t SET insee_declare = (
    SELECT c.insee FROM ref.commune c WHERE c.epci = '244400404' ORDER BY c.geom <-> t.geom LIMIT 1)
WHERE t.insee_declare IS NULL;

ANALYZE t_nantes;

-- Armoires. Quand une armoire alimente plusieurs communes, elle est rattachée à celle qui a le plus de points.
INSERT INTO metier.armoire (gestionnaire_id, code, code_source, insee, exploitant, geom, lot_id)
SELECT (SELECT id FROM t_gest), code_armoire, code_armoire,
       mode() WITHIN GROUP (ORDER BY insee_declare),
       mode() WITHIN GROUP (ORDER BY exploitant),
       ST_Centroid(ST_Collect(geom))::geometry(Point, 2154), min(lot_id)
FROM t_nantes GROUP BY code_armoire
ON CONFLICT (gestionnaire_id, code) DO UPDATE
    SET insee = EXCLUDED.insee, exploitant = EXCLUDED.exploitant, geom = EXCLUDED.geom, lot_id = EXCLUDED.lot_id, retire_le = NULL
    WHERE NOT metier.armoire.maj_locale
      AND ((metier.armoire.insee, metier.armoire.exploitant, metier.armoire.retire_le) IS DISTINCT FROM (EXCLUDED.insee, EXCLUDED.exploitant, NULL::date)
           OR NOT ST_Equals(metier.armoire.geom, EXCLUDED.geom));

ANALYZE metier.armoire;

INSERT INTO metier.depart (armoire_id, numero)
SELECT DISTINCT a.id, t.depart
FROM t_nantes t
JOIN metier.armoire a ON a.gestionnaire_id = (SELECT id FROM t_gest) AND a.code = t.code_armoire
WHERE t.depart IS NOT NULL
ON CONFLICT (armoire_id, numero) DO NOTHING;

ANALYZE metier.depart;

-- Supports : une ligne par identifiant, positionnée au centre de ses foyers.
INSERT INTO metier.support (gestionnaire_id, code, insee, armoire_id, voie, quartier, type_support, hauteur_m, saillie_m,
                            nature, forme, couleur, exploitant, geom, lot_id, ligne_source)
SELECT (SELECT id FROM t_gest), p.code_support, p.insee_declare, a.id, p.voie, p.quartier, p.type_support, p.hauteur_m, p.saillie_m,
       p.nature, p.forme, p.couleur, p.exploitant, g.geom, p.lot_id, p.ligne
FROM (SELECT DISTINCT ON (code_support) * FROM t_nantes ORDER BY code_support, ligne) p
JOIN (SELECT code_support, ST_Centroid(ST_Collect(geom))::geometry(Point, 2154) AS geom FROM t_nantes GROUP BY code_support) g USING (code_support)
JOIN metier.armoire a ON a.gestionnaire_id = (SELECT id FROM t_gest) AND a.code = p.code_armoire
ON CONFLICT (gestionnaire_id, code) DO UPDATE SET
    insee = EXCLUDED.insee, armoire_id = EXCLUDED.armoire_id, voie = EXCLUDED.voie, quartier = EXCLUDED.quartier,
    type_support = EXCLUDED.type_support, hauteur_m = EXCLUDED.hauteur_m, saillie_m = EXCLUDED.saillie_m, nature = EXCLUDED.nature,
    forme = EXCLUDED.forme, couleur = EXCLUDED.couleur, exploitant = EXCLUDED.exploitant, geom = EXCLUDED.geom,
    lot_id = EXCLUDED.lot_id, ligne_source = EXCLUDED.ligne_source, retire_le = NULL
WHERE NOT metier.support.maj_locale
  AND ((metier.support.insee, metier.support.armoire_id, metier.support.voie, metier.support.type_support, metier.support.hauteur_m,
        metier.support.nature, metier.support.exploitant, metier.support.retire_le)
       IS DISTINCT FROM (EXCLUDED.insee, EXCLUDED.armoire_id, EXCLUDED.voie, EXCLUDED.type_support, EXCLUDED.hauteur_m,
                         EXCLUDED.nature, EXCLUDED.exploitant, NULL::date)
       OR NOT ST_Equals(metier.support.geom, EXCLUDED.geom));

ANALYZE metier.support;

INSERT INTO metier.point_lumineux (gestionnaire_id, code, support_id, depart_id, insee, statut, eclairage_public, usage, type_source, structure,
                                   temperature_couleur, puissance_w, modele, hauteur_feu_m, flux_source_lm, nb_sources, designation_lampe,
                                   geom, lot_id, ligne_source)
SELECT s.gestionnaire_id, t.code_point, s.id, d.id, t.insee_declare, 'functional', t.eclairage_public, 'XX', t.type_source, t.structure,
       CASE WHEN t.temperature BETWEEN 1000 AND 10000 THEN t.temperature END, t.puissance_w, t.modele, t.hauteur_m, t.flux_source, t.nb_sources, t.designation,
       t.geom, t.lot_id, t.ligne
FROM t_nantes t
JOIN metier.support s ON s.gestionnaire_id = (SELECT id FROM t_gest) AND s.code = t.code_support
LEFT JOIN metier.depart d ON d.armoire_id = s.armoire_id AND d.numero = t.depart
ON CONFLICT (gestionnaire_id, code) DO UPDATE SET
    support_id = EXCLUDED.support_id, depart_id = EXCLUDED.depart_id, insee = EXCLUDED.insee, eclairage_public = EXCLUDED.eclairage_public,
    type_source = EXCLUDED.type_source, structure = EXCLUDED.structure, temperature_couleur = EXCLUDED.temperature_couleur,
    puissance_w = EXCLUDED.puissance_w, modele = EXCLUDED.modele, hauteur_feu_m = EXCLUDED.hauteur_feu_m, flux_source_lm = EXCLUDED.flux_source_lm,
    nb_sources = EXCLUDED.nb_sources, designation_lampe = EXCLUDED.designation_lampe, geom = EXCLUDED.geom, lot_id = EXCLUDED.lot_id,
    ligne_source = EXCLUDED.ligne_source, retire_le = NULL
WHERE NOT metier.point_lumineux.maj_locale
  AND ((metier.point_lumineux.support_id, metier.point_lumineux.depart_id, metier.point_lumineux.insee, metier.point_lumineux.eclairage_public,
        metier.point_lumineux.type_source, metier.point_lumineux.structure, metier.point_lumineux.temperature_couleur, metier.point_lumineux.puissance_w,
        metier.point_lumineux.modele, metier.point_lumineux.hauteur_feu_m, metier.point_lumineux.designation_lampe, metier.point_lumineux.retire_le)
       IS DISTINCT FROM (EXCLUDED.support_id, EXCLUDED.depart_id, EXCLUDED.insee, EXCLUDED.eclairage_public, EXCLUDED.type_source, EXCLUDED.structure,
                         EXCLUDED.temperature_couleur, EXCLUDED.puissance_w, EXCLUDED.modele, EXCLUDED.hauteur_feu_m, EXCLUDED.designation_lampe, NULL::date)
       OR NOT ST_Equals(metier.point_lumineux.geom, EXCLUDED.geom));

ANALYZE metier.point_lumineux;

UPDATE metier.point_lumineux p SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE p.gestionnaire_id = (SELECT id FROM t_gest) AND p.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_nantes t WHERE t.code_point = p.code);
UPDATE metier.support s SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE s.gestionnaire_id = (SELECT id FROM t_gest) AND s.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_nantes t WHERE t.code_support = s.code);
UPDATE metier.armoire a SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE a.gestionnaire_id = (SELECT id FROM t_gest) AND a.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_nantes t WHERE t.code_armoire = a.code);

COMMIT;
