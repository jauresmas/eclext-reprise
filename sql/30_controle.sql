-- Structure du contrôle : catalogue de règles, écarts, bilans.
-- Les familles reprennent les critères de qualité de la section 4.3 du géostandard (ISO 19157),
-- plus une famille propre à la reprise : ce qui est entré doit se retrouver à la sortie.

CREATE TABLE controle.regle (
    code       text PRIMARY KEY,
    famille    text NOT NULL,
    libelle    text NOT NULL,
    gravite    text NOT NULL CHECK (gravite IN ('bloquante', 'majeure', 'mineure', 'information')),
    traitement text NOT NULL
);

INSERT INTO controle.regle VALUES
('REP_01', 'Reprise', 'Le compte des lignes ne tombe pas juste entre la source et la base', 'bloquante', 'Aucune ligne ne doit se perdre : reprises + fusionnées + écartées = lignes du fichier'),
('REP_02', 'Reprise', 'La somme des puissances d''une armoire diffère de la source', 'bloquante', 'Relecture indépendante de la source, armoire par armoire'),
('REP_03', 'Reprise', 'Le comptage par commune diffère de la source', 'bloquante', 'Relecture indépendante de la source, commune par commune'),
('REP_04', 'Reprise', 'La reprise a déplacé un objet', 'bloquante', 'Position source reprojetée comparée à la position en base, seuil 1 cm'),
('EXH_01', 'Exhaustivité', 'Commune du territoire sans aucun objet', 'information', 'À indiquer dans les métadonnées, comme le demande la section 4.3'),
('EXH_02', 'Exhaustivité', 'Attribut obligatoire jamais renseigné par cette source', 'majeure', 'Laissé vide ou à XX ; rien n''est inventé. À demander au producteur'),
('COH_01', 'Cohérence logique', 'Valeur source absente des correspondances ou des listes', 'majeure', 'Mise à XX ou à vide en attendant une correspondance'),
('COH_02', 'Cohérence logique', 'Un même identifiant porté par deux objets différents', 'majeure', 'Les deux objets sont gardés, le second reçoit le suffixe -D2'),
('COH_03', 'Cohérence logique', 'Code de support hors du format habituel', 'mineure', 'Code gardé tel quel ; l''armoire est lue dans son préfixe'),
('COH_04', 'Cohérence logique', 'Support alimenté par plusieurs départs', 'information', 'Le départ est porté par le point lumineux : la base accepte ce cas. À vérifier'),
('COH_05', 'Cohérence logique', 'Armoire alimentant plusieurs communes', 'information', 'Armoire rattachée à la commune qui a le plus de points'),
('COH_06', 'Cohérence logique', 'Foyers d''un même support en désaccord sur la voie ou la hauteur', 'mineure', 'Le support garde la valeur du premier foyer'),
('COH_07', 'Cohérence logique', 'Ligne coupée à l''export et reconstituée', 'mineure', 'Fin de ligne recalée d''après la position de l''identifiant'),
('COH_08', 'Cohérence logique', 'Ligne coupée dont le début a disparu du fichier', 'majeure', 'Position et identifiant repris, matériel inconnu'),
('COH_09', 'Cohérence logique', 'Fragment de ligne inexploitable', 'mineure', 'Écarté, conservé dans controle.rejet'),
('COH_10', 'Cohérence logique', 'Type de lampe en désaccord avec la désignation', 'majeure', 'Type de lampe conservé'),
('POS_01', 'Précision de position', 'Objet à plus de 50 m de sa commune déclarée', 'mineure', 'Commune déclarée conservée'),
('POS_02', 'Précision de position', 'Objet à plus de 500 m de sa commune déclarée', 'majeure', 'Commune déclarée conservée'),
('POS_03', 'Précision de position', 'Deux supports à moins de 50 cm l''un de l''autre', 'mineure', 'Doublon probable, à trancher sur place'),
('POS_04', 'Précision de position', 'Support à plus de 2 km du centre de son armoire', 'mineure', 'Rattachement à vérifier'),
('POS_05', 'Précision de position', 'Publication située hors du territoire qu''elle annonce', 'bloquante', 'Objets conservés dans les communes où ils se trouvent. À signaler au producteur'),
('VAL_01', 'Exactitude thématique', 'Hauteur à 0', 'mineure', 'Comprise comme inconnue, laissée vide'),
('VAL_02', 'Exactitude thématique', 'Hauteur supérieure à 30 m', 'majeure', 'Gardée jusqu''à 60 m, laissée vide au-delà'),
('VAL_03', 'Exactitude thématique', 'Puissance à 0 ou supérieure à 1 000 W', 'mineure', 'Puissance à 0 laissée vide, puissance forte gardée'),
('VAL_04', 'Exactitude thématique', 'Température de couleur inexploitable', 'mineure', 'Hors de 1 000 à 10 000 K : laissée vide'),
('VAL_05', 'Exactitude thématique', 'Saillie vraisemblablement saisie en millimètres', 'mineure', 'Au-delà de 20 m : laissée vide, pas de conversion sans accord'),
('VAL_06', 'Exactitude thématique', 'Température de couleur incohérente avec le type de source', 'mineure', 'Valeur gardée ; sodium attendu entre 1 800 et 2 400 K'),
('VAL_07', 'Exactitude thématique', 'Puissance du foyer éloignée de celle de la désignation', 'majeure', 'Puissance du foyer gardée'),
('TEM_01', 'Qualité temporelle', 'Date par défaut 01/01/1970', 'mineure', 'Laissée vide'),
('TEM_02', 'Qualité temporelle', 'Date impossible', 'mineure', 'Laissée vide'),
('TEM_03', 'Qualité temporelle', 'Date postérieure à la collecte', 'majeure', 'Date gardée'),
('RAP_01', 'Rapprochement', 'Présent chez Cœur de France, absent du syndicat', 'majeure', 'Non repris : le syndicat fait référence. À vérifier'),
('RAP_02', 'Rapprochement', 'Présent au syndicat comme intercommunal, absent de Cœur de France', 'majeure', 'Gardé. À vérifier'),
('RAP_03', 'Rapprochement', 'Même position, code différent : recodage probable', 'mineure', 'Gardé sous le code du syndicat'),
('RAP_04', 'Rapprochement', 'Écart de position de plus de 5 m entre les deux publications', 'majeure', 'Position du syndicat gardée'),
('RAP_05', 'Rapprochement', 'Intercommunal chez Cœur de France, autre propriétaire au syndicat', 'mineure', 'Propriétaire du syndicat gardé');

CREATE TABLE controle.ecart (
    id              bigserial PRIMARY KEY,
    regle           text NOT NULL REFERENCES controle.regle,
    gestionnaire_id smallint REFERENCES metier.gestionnaire,
    table_objet     text,
    objet_id        bigint,
    code_objet      text,
    insee           char(5),
    valeur_lue      text,
    valeur_retenue  text,
    mesure          numeric,
    geom            geometry(Point, 2154),
    decision        text NOT NULL DEFAULT 'a_traiter' CHECK (decision IN ('a_traiter', 'confirmee', 'faux_positif', 'corrigee')),
    commentaire     text,
    traite_par      text,
    traite_le       timestamptz
);
COMMENT ON TABLE controle.ecart IS 'Un écart par objet et par règle. Relancer les contrôles conserve les décisions déjà prises.';
CREATE INDEX ecart_regle ON controle.ecart (regle);
CREATE INDEX ecart_geom ON controle.ecart USING gist (geom);
CREATE INDEX ecart_insee ON controle.ecart (insee);

CREATE TABLE controle.rapprochement (
    insee        char(5),
    commune      text NOT NULL,
    code         text NOT NULL,
    statut       text NOT NULL CHECK (statut IN ('apparie', 'absent_syndicat', 'absent_ccf', 'recode_probable')),
    distance_m   numeric,
    code_syndicat text,
    client_syndicat text,
    rue          text,
    geom_ccf     geometry(Point, 2154),
    geom_syndicat geometry(Point, 2154)
);
COMMENT ON TABLE controle.rapprochement IS 'Comparaison objet par objet de la publication Cœur de France et de celle du syndicat du Cher.';

CREATE VIEW controle.bilan_regle AS
SELECT r.code, r.famille, r.libelle, r.gravite, g.code AS gestionnaire, count(e.id) AS nb_ecarts,
       count(e.id) FILTER (WHERE e.decision = 'a_traiter') AS a_traiter
FROM controle.regle r
LEFT JOIN controle.ecart e ON e.regle = r.code
LEFT JOIN metier.gestionnaire g ON g.id = e.gestionnaire_id
GROUP BY r.code, r.famille, r.libelle, r.gravite, g.code
ORDER BY r.code, g.code;

-- Conformité au géostandard, attribut par attribut.
-- renseigne : valeur présente et différente de XX ou AU, donc une information réelle
-- conforme   : valeur présente et dans la liste (XX compte : le standard l'admet pour les listes)
CREATE VIEW controle.conformite_attribut AS
SELECT p.gestionnaire, a.attribut, a.obligatoire,
       count(*) AS points,
       count(*) FILTER (WHERE a.valeur IS NOT NULL) AS conformes,
       count(*) FILTER (WHERE a.valeur IS NOT NULL AND a.valeur NOT IN ('XX', 'AU')) AS renseignes,
       round(100.0 * count(*) FILTER (WHERE a.valeur IS NOT NULL) / count(*), 1) AS taux_conforme,
       round(100.0 * count(*) FILTER (WHERE a.valeur IS NOT NULL AND a.valeur NOT IN ('XX', 'AU')) / count(*), 1) AS taux_renseigne,
       coalesce(o.origine, 'absent') AS origine,
       o.champ_source,
       o.commentaire
FROM eclext.pointlumineux p
CROSS JOIN LATERAL (VALUES
    ('statut', true, p.statut),
    ('eclairagePublic', true, p."eclairagePublic"::text),
    ('usage', true, p.usage),
    ('typeSource', true, p."typeSource"),
    ('structure', true, p.structure),
    ('support', true, p.support),
    ('temperatureCouleur', true, p."temperatureCouleur"::text),
    ('puissance', true, p.puissance::text),
    ('valideDe', true, p."valideDe"),
    ('extinctionNuit', true, p."extinctionNuit"::text),
    ('estAdaptatif', true, p."estAdaptatif"::text),
    ('fabricant', false, p.fabricant),
    ('modele', false, p.modele),
    ('hauteurFeu', false, p."hauteurFeu"::text),
    ('fluxSource', false, p."fluxSource"::text),
    ('datePremiereInstallation', false, p."datePremiereInstallation"),
    ('eclairageAdaptatif', false, p."eclairageAdaptatif")
) AS a(attribut, obligatoire, valeur)
LEFT JOIN ref.origine_attribut o ON o.gestionnaire = p.gestionnaire AND o.attribut = a.attribut
GROUP BY p.gestionnaire, a.attribut, a.obligatoire, o.origine, o.champ_source, o.commentaire;

-- Synthèse par source : part d'obligatoires renseignés, points complets au sens du standard
CREATE VIEW controle.conformite_source AS
SELECT p.gestionnaire,
       count(*) AS points,
       count(*) FILTER (WHERE p."eclairagePublic" IS NOT NULL AND p."temperatureCouleur" IS NOT NULL AND p.puissance IS NOT NULL
                          AND p."valideDe" IS NOT NULL AND p."extinctionNuit" IS NOT NULL AND p."estAdaptatif" IS NOT NULL) AS points_conformes,
       count(*) FILTER (WHERE p."eclairagePublic" IS NOT NULL AND p."temperatureCouleur" IS NOT NULL AND p.puissance IS NOT NULL
                          AND p."valideDe" IS NOT NULL AND p."extinctionNuit" IS NOT NULL AND p."estAdaptatif" IS NOT NULL
                          AND p.usage NOT IN ('XX', 'AU') AND p."typeSource" NOT IN ('XX', 'AU')
                          AND p.structure NOT IN ('XX', 'AU') AND p.support NOT IN ('XX', 'AU')) AS points_sans_inconnue
FROM eclext.pointlumineux p
GROUP BY p.gestionnaire;
