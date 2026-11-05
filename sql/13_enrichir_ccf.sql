-- La communauté de communes Cœur de France publie une partie des objets du syndicat du Cher.
-- Sa publication n'entre pas comme une source de plus (ce seraient des doublons) : elle sert à
-- contrôler la position et le code (32_rapprochement.sql) et apporte ce qui manque au syndicat,
-- le nom de la voie et l'altitude.

BEGIN;
SET LOCAL app.reprise = 'on';

-- L'altitude est comparée à la précision de sa colonne : sinon, une valeur arrondie paraît toujours
-- différente de la source et la ligne est réécrite à chaque passe.
UPDATE metier.support s
SET voie = nullif(trim(c.rue), ''),
    z_m  = ref.vers_nombre(c.z)::numeric(7,2)
FROM src.ccf c
JOIN flux.lot l ON l.id = c.lot_id AND l.courant
JOIN ref.commune m ON ref.normaliser(m.nom) = ref.normaliser(c.commune) AND m.departement = '18'
WHERE s.code = m.insee || '-' || c.code_point_lumineux
  AND s.gestionnaire_id = (SELECT id FROM metier.gestionnaire WHERE code = 'SDE18')
  AND NOT s.maj_locale
  AND (s.voie, s.z_m) IS DISTINCT FROM (nullif(trim(c.rue), ''), ref.vers_nombre(c.z)::numeric(7,2));

COMMIT;
