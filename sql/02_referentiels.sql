-- Listes de valeurs et référentiels.
-- Les listes EclExt reprennent la section 3.7 du géostandard CNIG (v1.1, 29 novembre 2022).

CREATE TABLE ref.commune (
    insee       char(5) PRIMARY KEY,
    nom         text NOT NULL,
    departement text NOT NULL,
    epci        text,
    geom        geometry(MultiPolygon, 2154) NOT NULL
);
CREATE INDEX commune_geom ON ref.commune USING gist (geom);

-- Nom de commune ramené à une forme comparable : BRUERE-ALLICHAMPS = Bruère-Allichamps
CREATE FUNCTION ref.normaliser(texte text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT trim(regexp_replace(upper(unaccent(texte)), '[^A-Z0-9]+', ' ', 'g'))
$$;

-- Conversions prudentes : une valeur illisible donne NULL (et un écart de contrôle), jamais une erreur
CREATE FUNCTION ref.vers_nombre(texte text) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN trim(texte) ~ '^-?[0-9]+([.,][0-9]+)?$' THEN replace(trim(texte), ',', '.')::numeric END
$$;

CREATE FUNCTION ref.vers_date(texte text) RETURNS date
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF texte ~ '^\d{8}$' THEN RETURN to_date(texte, 'YYYYMMDD');
    ELSIF texte ~ '^\d{2}/\d{2}/\d{4}$' THEN RETURN to_date(texte, 'DD/MM/YYYY');
    ELSIF texte ~ '^\d{4}-\d{2}-\d{2}$' THEN RETURN texte::date;
    END IF;
    RETURN NULL;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$;

CREATE FUNCTION ref.vers_booleen(texte text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE upper(trim(texte)) WHEN 'OUI' THEN true WHEN 'NON' THEN false END
$$;

-- Listes EclExt ------------------------------------------------------------------------------
CREATE TABLE ref.usage (code varchar(2) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.usage VALUES
    ('A',  'Sécurité des déplacements, des personnes et des biens, confort des usagers'),
    ('B1', 'Mise en lumière du patrimoine'),
    ('B2', 'Mise en lumière du cadre bâti'),
    ('B3', 'Mise en lumière des parcs et jardins'),
    ('B4', 'Mise en lumière d''un élément naturel'),
    ('C',  'Équipements sportifs de plein air ou découvrables'),
    ('D',  'Bâtiments non résidentiels'),
    ('E',  'Parcs de stationnement non couverts ou semi-couverts'),
    ('F',  'Événementiel extérieur'),
    ('G',  'Chantiers en extérieur'),
    ('PU', 'Publicité'),
    ('IN', 'Diffusion d''information'),
    ('AU', 'Autre'),
    ('XX', 'Valeur inconnue');

CREATE TABLE ref.type_source (code varchar(5) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.type_source VALUES
    ('FLUO', 'Fluorescence'), ('HAL', 'Halogène'), ('IM', 'Iodures métalliques'),
    ('INC', 'Incandescence'), ('IND', 'Induction'), ('LED', 'Diode électroluminescente'),
    ('SBP', 'Sodium basse pression'), ('SHP', 'Sodium haute pression'),
    ('VM', 'Vapeur de mercure'), ('XEN', 'Xénon'), ('AU', 'Autre'), ('XX', 'Valeur inconnue');

CREATE TABLE ref.structure_luminaire (code varchar(4) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.structure_luminaire VALUES
    ('APP', 'Applique'), ('BOR', 'Borne'), ('BL', 'Boule lumineuse'), ('COL', 'Colonne'),
    ('EN', 'Encastré'), ('LANT', 'Lanterne'), ('PROJ', 'Projecteur'), ('REGL', 'Réglette'),
    ('TUBE', 'Tube'), ('VASQ', 'Vasque'), ('AU', 'Autre'), ('XX', 'Valeur inconnue');

CREATE TABLE ref.support_luminaire (code varchar(3) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.support_luminaire VALUES
    ('BUS', 'Abribus'), ('CAT', 'Caténaire'), ('ENS', 'Enseigne'), ('MAT', 'Mât'), ('MUR', 'Mur'),
    ('OUV', 'Ouvrage'), ('PAN', 'Panneau'), ('POT', 'Poteau'), ('SOL', 'Sol'),
    ('AU', 'Autre'), ('XX', 'Valeur inconnue');

CREATE TABLE ref.eclairage_adaptatif (code varchar(2) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.eclairage_adaptatif VALUES
    ('AV', 'Action volontaire de l''usager'), ('CO', 'Comportement des usagers'),
    ('EN', 'Environnement'), ('TG', 'Télégestion');

CREATE TABLE ref.grandeur_variation (code varchar(2) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.grandeur_variation VALUES
    ('EX', 'Extinction totale'), ('F', 'Flux'), ('P', 'Puissance'), ('TC', 'Température de couleur');

CREATE TABLE ref.format_variation (code varchar(2) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.format_variation VALUES ('%', 'Pourcentage'), ('VA', 'Valeur absolue');

CREATE TABLE ref.statut_installation (code text PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.statut_installation VALUES
    ('decommissioned', 'Hors service'), ('dismantled', 'Déposé'), ('functional', 'En service'),
    ('projected', 'Projeté'), ('underCommissionning', 'En attente de mise en service'),
    ('underConstruction', 'En construction');

-- Nomenclatures internes ----------------------------------------------------------------------
CREATE TABLE ref.etat_support (code text PRIMARY KEY, description text NOT NULL, ordre smallint NOT NULL);
INSERT INTO ref.etat_support VALUES
    ('NEUF', 'Neuf', 1), ('BON', 'Bon', 2), ('MOYEN', 'Moyen', 3), ('MAUVAIS', 'Mauvais', 4), ('VETUSTE', 'Vétuste', 5);

CREATE TABLE ref.type_pose (code text PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.type_pose VALUES
    ('MASSIF', 'Sur massif'), ('ENCASTRE', 'Encastré'), ('FACADE', 'Sur façade'),
    ('SUSPENDU', 'Suspendu'), ('AUTRE', 'Autre');

CREATE TABLE ref.type_massif (code text PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.type_massif VALUES
    ('PREFABRIQUE', 'Massif préfabriqué'), ('COULE', 'Massif coulé en place'),
    ('BETON', 'Béton, mode de réalisation non précisé'), ('MURET', 'Muret'), ('SANS', 'Sans massif');

CREATE TABLE ref.classe_precision (code char(1) PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.classe_precision VALUES
    ('A', 'Classe A : incertitude inférieure ou égale à 40 cm'),
    ('B', 'Classe B : incertitude inférieure ou égale à 1,5 m'),
    ('C', 'Classe C : incertitude supérieure à 1,5 m');

CREATE TABLE ref.proprietaire (code text PRIMARY KEY, description text NOT NULL);
INSERT INTO ref.proprietaire VALUES
    ('COMMUNE', 'Commune'), ('EPCI', 'Intercommunalité'), ('METROPOLE', 'Métropole'), ('PRIVE', 'Privé');

-- Correspondances source vers cible ----------------------------------------------------------
-- Chargées depuis data/correspondances/*.csv : c'est le document que le gestionnaire relit.
-- certitude = 'certain' : la valeur source dit la même chose que la valeur cible
-- certitude = 'deduit'  : déduction raisonnable, à faire valider par le gestionnaire
-- certitude = 'arbitrage' : la source est ambiguë, la cible reste inconnue tant que personne n'a tranché
CREATE TABLE ref.correspondance (
    source        text NOT NULL,
    champ_source  text NOT NULL,
    valeur_source text NOT NULL,
    attribut_cible text NOT NULL,
    valeur_cible  text,
    certitude     text NOT NULL CHECK (certitude IN ('certain', 'deduit', 'arbitrage')),
    commentaire   text,
    PRIMARY KEY (source, champ_source, valeur_source, attribut_cible)
);
CREATE INDEX correspondance_cible ON ref.correspondance (attribut_cible);

-- Origine de chaque attribut EclExt, par source : lue pour dire ce que vaut l'information exportée.
-- origine : direct, converti, deduit, hypothese, absent
CREATE TABLE ref.origine_attribut (
    gestionnaire text NOT NULL,
    attribut     text NOT NULL,
    origine      text NOT NULL CHECK (origine IN ('direct', 'converti', 'deduit', 'hypothese', 'absent')),
    champ_source text,
    commentaire  text,
    PRIMARY KEY (gestionnaire, attribut)
);
