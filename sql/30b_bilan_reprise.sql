-- Vue créée après le chargement : elle lit les tables du schéma src.
-- Bilan d'exhaustivité de la reprise : chaque ligne du fichier est reprise, fusionnée ou écartée
CREATE OR REPLACE VIEW controle.bilan_reprise AS
WITH lots AS (SELECT source, id AS lot_id FROM flux.lot WHERE courant),
source AS (
    SELECT 'sde18' AS source, count(*) AS lignes FROM src.sde18 s JOIN lots l ON l.lot_id = s.lot_id
    UNION ALL SELECT 'nantes', count(*) FROM src.nantes s JOIN lots l ON l.lot_id = s.lot_id
    UNION ALL SELECT 'loire', count(*) FROM src.loire s JOIN lots l ON l.lot_id = s.lot_id
),
cible AS (
    SELECT g.source, count(*) FILTER (WHERE p.retire_le IS NULL) AS points, count(DISTINCT p.support_id) FILTER (WHERE p.retire_le IS NULL) AS supports
    FROM metier.point_lumineux p JOIN metier.gestionnaire g ON g.id = p.gestionnaire_id GROUP BY g.source
),
rejets AS (
    SELECT l.source,
           count(*) FILTER (WHERE r.motif LIKE 'fusionnee%') AS fusionnees,
           count(*) FILTER (WHERE r.motif NOT LIKE 'fusionnee%') AS ecartees
    FROM controle.rejet r JOIN lots l ON l.lot_id = r.lot_id GROUP BY l.source
)
SELECT g.code AS gestionnaire, s.lignes AS lignes_source, c.points AS points_repris, c.supports AS supports_repris,
       coalesce(r.fusionnees, 0) AS lignes_fusionnees, coalesce(r.ecartees, 0) AS lignes_ecartees,
       s.lignes - c.points - coalesce(r.fusionnees, 0) - coalesce(r.ecartees, 0) AS ecart
FROM metier.gestionnaire g
JOIN source s USING (source)
JOIN cible c USING (source)
LEFT JOIN rejets r USING (source);

GRANT SELECT ON controle.bilan_reprise TO ep_administrateur;
