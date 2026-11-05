-- Jeu d'essai de la recette. Les sources retenues ne publient aucun historique de maintenance : les
-- signalements et interventions ci-dessous sont créés pour tester les fiches et les droits, sur de vrais
-- objets du patrimoine, et portent tous jeu_essai = true. Ils ne changent aucun attribut d'EclExt :
-- les interventions qui changent le matériel sont testées dans une transaction annulée (tests/).

BEGIN;

DELETE FROM exploitation.intervention WHERE jeu_essai;
DELETE FROM exploitation.signalement WHERE jeu_essai;

INSERT INTO admin.entreprise (nom) VALUES ('Entreprise A, jeu d''essai'), ('Entreprise B, jeu d''essai')
ON CONFLICT (nom) DO NOTHING;

-- Une commune de la métropole nantaise, dont la source décrit le matériel, et une entreprise qui y intervient avec une commune voisine
SELECT admin.creer_compte('demo_commune', 'ep_collectivite', ARRAY['44143']::char(5)[]);
SELECT admin.creer_compte('demo_entreprise', 'ep_entreprise', ARRAY['44143', '44020']::char(5)[],
                          (SELECT id FROM admin.entreprise WHERE nom LIKE 'Entreprise A%'));
SELECT admin.creer_compte('demo_entreprise_b', 'ep_entreprise', ARRAY['44215']::char(5)[],
                          (SELECT id FROM admin.entreprise WHERE nom LIKE 'Entreprise B%'));

-- Signalements sur des points réels de la commune
INSERT INTO exploitation.signalement (point_id, nature, description, declarant, jeu_essai, insee, geom)
SELECT p.id, n.nature, n.description, 'demo_commune', true, p.insee, p.geom
FROM (SELECT id, insee, geom, row_number() OVER (ORDER BY code) AS rang
      FROM metier.point_lumineux WHERE insee = '44143' AND retire_le IS NULL ORDER BY code LIMIT 8) p
JOIN (VALUES (1, 'PANNE', 'Éteint depuis trois jours'),
             (2, 'PANNE', 'Rue éteinte sur une cinquantaine de mètres'),
             (3, 'ALLUME_JOUR', 'Reste allumé en journée'),
             (4, 'CLIGNOTE', 'Clignote la nuit'),
             (5, 'CASSE', 'Mât heurté par un véhicule'),
             (6, 'SECURITE', 'Porte de mât ouverte, câbles accessibles'),
             (7, 'PANNE', 'Signalé par un riverain'),
             (8, 'AUTRE', 'Branche sur le luminaire')) AS n(rang, nature, description) USING (rang);

-- Interventions dans différents états, confiées à l'entreprise A
INSERT INTO exploitation.intervention (signalement_id, point_id, entreprise_id, nature, date_prevue, cree_par, jeu_essai, insee, geom)
SELECT s.id, s.point_id, (SELECT id FROM admin.entreprise WHERE nom LIKE 'Entreprise A%'),
       CASE WHEN s.nature = 'CASSE' THEN 'ENTRETIEN' ELSE 'DEPANNAGE' END,
       current_date + 3 + row_number() OVER (ORDER BY s.id)::integer, 'demo_admin', true, s.insee, s.geom
FROM exploitation.signalement s
WHERE s.jeu_essai AND s.nature IN ('PANNE', 'CLIGNOTE', 'CASSE');

UPDATE exploitation.intervention SET etat = 'PLANIFIEE' WHERE jeu_essai AND id IN (SELECT id FROM exploitation.intervention WHERE jeu_essai ORDER BY id LIMIT 3);
UPDATE exploitation.intervention SET etat = 'EN_COURS' WHERE jeu_essai AND id IN (SELECT id FROM exploitation.intervention WHERE jeu_essai ORDER BY id LIMIT 2);
UPDATE exploitation.intervention SET etat = 'REALISEE', date_realisee = current_date, compte_rendu = 'Lampe remplacée à l''identique, essai d''allumage correct'
WHERE jeu_essai AND id = (SELECT min(id) FROM exploitation.intervention WHERE jeu_essai);

-- Et une intervention d'une autre entreprise, sur une autre commune : invisible pour l'entreprise A
INSERT INTO exploitation.intervention (point_id, entreprise_id, nature, cree_par, jeu_essai, insee, geom)
SELECT p.id, (SELECT id FROM admin.entreprise WHERE nom LIKE 'Entreprise B%'), 'CONTROLE', 'demo_admin', true, p.insee, p.geom
FROM metier.point_lumineux p WHERE p.insee = '44215' AND p.retire_le IS NULL ORDER BY p.code LIMIT 1;

COMMIT;
