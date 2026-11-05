-- Reprise de la publication sur le département de la Loire, déjà rangée selon les colonnes d'EclExt.
--
-- Un retour à la ligne dans le champ modele a coupé des lignes à l'export :
--   début   En service | OUI | A | LED | PROJ | MUR | 4000 | 26 | | Burst Compact | (rien ensuite)
--   fin     "Powercore" | 3.5 | 550 | 31/12/2018 | NON | NON | | 970665,66 | 6560620,75 | identifiant
-- La fin de ligne est décalée, et son début a parfois disparu du fichier. La position de l'identifiant
-- dans la ligne donne le décalage : X et Y sont juste avant, la hauteur et le flux plus loin.
-- Une ligne sans identifiant ni coordonnées lisibles est écartée avec son motif (controle.rejet).

BEGIN;
SET LOCAL app.reprise = 'on';

CREATE TEMP TABLE t_lot ON COMMIT DROP AS
    SELECT id AS lot_id, to_date(date_collecte, 'YYYYMMDD') AS date_collecte FROM flux.lot WHERE source = 'loire' AND courant;
CREATE TEMP TABLE t_gest ON COMMIT DROP AS SELECT id FROM metier.gestionnaire WHERE code = 'LOIRE';

CREATE TEMP TABLE t_brut ON COMMIT DROP AS
SELECT l.lot_id, l.ligne, l.id,
       ARRAY[l.statut, l.eclairagepublic, l.usage, l.typesource, l.structure, l.support, l.temperaturecouleur, l.puissance,
             l.fabricant, l.modele, l.hauteurfeu, l.fluxsource, l.datepremieinstallation, l.extinctionnuit, l.estadaptatif,
             l.eclairageadaptatif, l.x, l.y, l.id] AS c
FROM src.loire l JOIN t_lot USING (lot_id);

-- Lignes complètes
CREATE TEMP TABLE t_loire ON COMMIT DROP AS
SELECT lot_id, ligne, 'complete' AS etat_ligne, id AS code,
       c[1] statut, c[2] eclairagepublic, c[3] usage, c[4] typesource, c[5] structure, c[6] support, c[7] temperature,
       c[8] puissance, c[9] fabricant, c[10] modele, c[11] hauteur, c[12] flux, c[13] date_install, c[14] extinction,
       c[15] adaptatif, c[16] type_adaptatif, c[17] x, c[18] y
FROM t_brut WHERE id <> '';

-- Fins de ligne décalées : position de l'identifiant, puis début de ligne s'il précède immédiatement
INSERT INTO t_loire
SELECT f.lot_id, f.ligne,
       CASE WHEN d.ligne IS NOT NULL THEN 'recollee' ELSE 'debut_perdu' END,
       f.c[p.i],
       coalesce(d.c[1], 'En service'), d.c[2], d.c[3], d.c[4], d.c[5], d.c[6], d.c[7], d.c[8], d.c[9], d.c[10],
       CASE WHEN p.i >= 9 THEN f.c[p.i - 8] END, CASE WHEN p.i >= 8 THEN f.c[p.i - 7] END, CASE WHEN p.i >= 7 THEN f.c[p.i - 6] END,
       CASE WHEN p.i >= 6 THEN f.c[p.i - 5] END, CASE WHEN p.i >= 5 THEN f.c[p.i - 4] END, CASE WHEN p.i >= 4 THEN f.c[p.i - 3] END,
       f.c[p.i - 2], f.c[p.i - 1]
FROM t_brut f
CROSS JOIN LATERAL (
    SELECT i FROM generate_subscripts(f.c, 1) i
    WHERE f.c[i] ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' LIMIT 1
) p
LEFT JOIN t_brut d ON d.ligne = f.ligne - 1 AND d.id = '' AND d.c[1] = 'En service'
WHERE f.id = '' AND p.i >= 3
  AND ref.vers_nombre(f.c[p.i - 2]) BETWEEN 700000 AND 1100000
  AND ref.vers_nombre(f.c[p.i - 1]) BETWEEN 6200000 AND 6700000;

-- Le reste : débuts de ligne repris avec leur fin, ou fragments inexploitables
DELETE FROM controle.rejet r USING t_lot l WHERE r.lot_id = l.lot_id;
INSERT INTO controle.rejet (lot_id, ligne, motif, contenu)
SELECT b.lot_id, b.ligne,
       CASE WHEN EXISTS (SELECT 1 FROM t_loire t WHERE t.ligne = b.ligne + 1 AND t.etat_ligne = 'recollee')
            THEN 'fusionnee : début de ligne recollé à la ligne suivante'
            ELSE 'fragment sans identifiant ni coordonnées lisibles' END,
       to_jsonb(b.c)
FROM t_brut b
WHERE b.id = '' AND NOT EXISTS (SELECT 1 FROM t_loire t WHERE t.ligne = b.ligne);

-- Identifiants portés par plusieurs lignes : le code doit rester unique
UPDATE t_loire t SET code = t.code || '-D' || d.rang
FROM (SELECT ligne, row_number() OVER (PARTITION BY code ORDER BY ligne) AS rang FROM t_loire) d
WHERE d.ligne = t.ligne AND d.rang > 1;

CREATE TEMP TABLE t_points ON COMMIT DROP AS
SELECT t.*, ST_SetSRID(ST_MakePoint(ref.vers_nombre(t.x)::float8, ref.vers_nombre(t.y)::float8), 2154)::geometry(Point, 2154) AS geom FROM t_loire t;
CREATE INDEX ON t_points USING gist (geom);
ANALYZE t_points;

-- La source ne donne pas la commune : celle qui contient le point, ou à défaut la plus proche.
-- Le titre annonce la Loire, mais les coordonnées tombent en Haute-Savoie : on suit la position
-- et la règle POS_05 signale le désaccord au lieu de le masquer.
ALTER TABLE t_points ADD COLUMN insee char(5);
UPDATE t_points t SET insee = c.insee FROM ref.commune c WHERE ST_Within(t.geom, c.geom);
UPDATE t_points t SET insee = (SELECT c.insee FROM ref.commune c ORDER BY c.geom <-> t.geom LIMIT 1)
WHERE t.insee IS NULL;

ANALYZE t_points;

INSERT INTO metier.support (gestionnaire_id, code, insee, type_support, hauteur_m, geom, lot_id, ligne_source)
SELECT (SELECT id FROM t_gest), t.code, t.insee,
       CASE WHEN t.support IN (SELECT code FROM ref.support_luminaire) THEN t.support ELSE 'XX' END,
       CASE WHEN ref.vers_nombre(t.hauteur) > 0 AND ref.vers_nombre(t.hauteur) <= 60 THEN ref.vers_nombre(t.hauteur) END,
       t.geom, t.lot_id, t.ligne
FROM t_points t
ON CONFLICT (gestionnaire_id, code) DO UPDATE SET
    insee = EXCLUDED.insee, type_support = EXCLUDED.type_support, hauteur_m = EXCLUDED.hauteur_m, geom = EXCLUDED.geom,
    lot_id = EXCLUDED.lot_id, ligne_source = EXCLUDED.ligne_source, retire_le = NULL
WHERE NOT metier.support.maj_locale
  AND ((metier.support.insee, metier.support.type_support, metier.support.hauteur_m, metier.support.ligne_source, metier.support.retire_le)
       IS DISTINCT FROM (EXCLUDED.insee, EXCLUDED.type_support, EXCLUDED.hauteur_m, EXCLUDED.ligne_source, NULL::date)
       OR NOT ST_Equals(metier.support.geom, EXCLUDED.geom));

ANALYZE metier.support;

INSERT INTO metier.point_lumineux (gestionnaire_id, code, support_id, insee, statut, eclairage_public, usage, type_source, structure,
                                   temperature_couleur, puissance_w, extinction_nuit, est_adaptatif, eclairage_adaptatif, fabricant, modele,
                                   hauteur_feu_m, flux_source_lm, date_premiere_installation, geom, lot_id, ligne_source)
SELECT s.gestionnaire_id, t.code, s.id, t.insee, 'functional',
       ref.vers_booleen(t.eclairagepublic),
       CASE WHEN t.usage IN (SELECT code FROM ref.usage) THEN t.usage ELSE 'XX' END,
       CASE WHEN t.typesource IN (SELECT code FROM ref.type_source) THEN t.typesource ELSE 'XX' END,
       CASE WHEN t.structure IN (SELECT code FROM ref.structure_luminaire) THEN t.structure ELSE 'XX' END,
       CASE WHEN ref.vers_nombre(t.temperature) BETWEEN 1000 AND 10000 THEN ref.vers_nombre(t.temperature)::integer END,
       CASE WHEN ref.vers_nombre(t.puissance) > 0 THEN ref.vers_nombre(t.puissance) END,
       ref.vers_booleen(t.extinction), ref.vers_booleen(t.adaptatif),
       CASE WHEN t.type_adaptatif IN (SELECT code FROM ref.eclairage_adaptatif) AND ref.vers_booleen(t.adaptatif) IS NOT FALSE THEN t.type_adaptatif END,
       nullif(trim(t.fabricant), ''),
       nullif(nullif(trim(t.modele), ''), 'INCONNU'),
       CASE WHEN ref.vers_nombre(t.hauteur) > 0 AND ref.vers_nombre(t.hauteur) <= 60 THEN ref.vers_nombre(t.hauteur) END,
       CASE WHEN ref.vers_nombre(t.flux) > 0 THEN ref.vers_nombre(t.flux) END,
       CASE WHEN ref.vers_date(t.date_install) >= DATE '1900-01-01' THEN ref.vers_date(t.date_install) END,
       t.geom, t.lot_id, t.ligne
FROM t_points t
JOIN metier.support s ON s.gestionnaire_id = (SELECT id FROM t_gest) AND s.code = t.code
ON CONFLICT (gestionnaire_id, code) DO UPDATE SET
    support_id = EXCLUDED.support_id, insee = EXCLUDED.insee, eclairage_public = EXCLUDED.eclairage_public, usage = EXCLUDED.usage,
    type_source = EXCLUDED.type_source, structure = EXCLUDED.structure, temperature_couleur = EXCLUDED.temperature_couleur,
    puissance_w = EXCLUDED.puissance_w, extinction_nuit = EXCLUDED.extinction_nuit, est_adaptatif = EXCLUDED.est_adaptatif,
    eclairage_adaptatif = EXCLUDED.eclairage_adaptatif, fabricant = EXCLUDED.fabricant, modele = EXCLUDED.modele,
    hauteur_feu_m = EXCLUDED.hauteur_feu_m, flux_source_lm = EXCLUDED.flux_source_lm,
    date_premiere_installation = EXCLUDED.date_premiere_installation, geom = EXCLUDED.geom, lot_id = EXCLUDED.lot_id,
    ligne_source = EXCLUDED.ligne_source, retire_le = NULL
WHERE NOT metier.point_lumineux.maj_locale
  AND ((metier.point_lumineux.insee, metier.point_lumineux.eclairage_public, metier.point_lumineux.usage, metier.point_lumineux.type_source,
        metier.point_lumineux.structure, metier.point_lumineux.temperature_couleur, metier.point_lumineux.puissance_w, metier.point_lumineux.extinction_nuit,
        metier.point_lumineux.est_adaptatif, metier.point_lumineux.modele, metier.point_lumineux.hauteur_feu_m, metier.point_lumineux.flux_source_lm,
        metier.point_lumineux.date_premiere_installation, metier.point_lumineux.ligne_source, metier.point_lumineux.retire_le)
       IS DISTINCT FROM (EXCLUDED.insee, EXCLUDED.eclairage_public, EXCLUDED.usage, EXCLUDED.type_source, EXCLUDED.structure, EXCLUDED.temperature_couleur,
                         EXCLUDED.puissance_w, EXCLUDED.extinction_nuit, EXCLUDED.est_adaptatif, EXCLUDED.modele, EXCLUDED.hauteur_feu_m, EXCLUDED.flux_source_lm,
                         EXCLUDED.date_premiere_installation, EXCLUDED.ligne_source, NULL::date)
       OR NOT ST_Equals(metier.point_lumineux.geom, EXCLUDED.geom));

ANALYZE metier.point_lumineux;

UPDATE metier.point_lumineux p SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE p.gestionnaire_id = (SELECT id FROM t_gest) AND p.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_points t WHERE t.code = p.code);
UPDATE metier.support s SET retire_le = (SELECT date_collecte FROM t_lot)
WHERE s.gestionnaire_id = (SELECT id FROM t_gest) AND s.retire_le IS NULL
  AND NOT EXISTS (SELECT 1 FROM t_points t WHERE t.code = s.code);

COMMIT;
