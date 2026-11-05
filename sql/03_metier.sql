-- Base métier de l'éclairage public.
--
-- Le géostandard EclExt est un format d'échange : sa section 4.1 laisse au gestionnaire le choix de
-- sa structure interne. Celle-ci sépare ce que les inventaires mélangent : l'armoire, le départ,
-- le support et le point lumineux. Les vues du schéma eclext en tirent le format d'échange.

CREATE TABLE metier.gestionnaire (
    id     smallserial PRIMARY KEY,
    code   text NOT NULL UNIQUE,
    nom    text NOT NULL,
    siren  char(9),
    source text NOT NULL UNIQUE,
    territoire_annonce text NOT NULL
);
COMMENT ON TABLE metier.gestionnaire IS 'Producteur de la donnée reprise (rôle gestionnaire ou exploitant au sens d''EclExt).';
COMMENT ON COLUMN metier.gestionnaire.territoire_annonce IS 'Département annoncé par la publication, comparé à la position des objets (règle POS_05).';
INSERT INTO metier.gestionnaire (code, nom, siren, source, territoire_annonce) VALUES
    ('SDE18',  'Syndicat départemental d''énergie du Cher', '241800549', 'sde18', '18'),
    ('NANTES', 'Nantes Métropole', '244400404', 'nantes', '44'),
    ('LOIRE',  'Publication « Éclairage public sur le département de la Loire », déposée par Loire Forez Agglomération', '200065886', 'loire', '42');

CREATE TABLE metier.armoire (
    id              serial PRIMARY KEY,
    gestionnaire_id smallint NOT NULL REFERENCES metier.gestionnaire,
    code            text NOT NULL,
    code_source     text NOT NULL,
    insee           char(5) REFERENCES ref.commune,
    exploitant      text,
    geom            geometry(Point, 2154),
    position_estimee boolean NOT NULL DEFAULT true,
    lot_id          integer NOT NULL REFERENCES flux.lot,
    retire_le       date,
    maj_locale      boolean NOT NULL DEFAULT false,
    UNIQUE (gestionnaire_id, code)
);
COMMENT ON TABLE metier.armoire IS 'Armoire de commande. Aucune source reprise ne publie sa position : geom est le barycentre des supports qu''elle alimente.';
CREATE INDEX armoire_geom ON metier.armoire USING gist (geom);
CREATE INDEX armoire_insee ON metier.armoire (insee);

CREATE TABLE metier.depart (
    id         serial PRIMARY KEY,
    armoire_id integer NOT NULL REFERENCES metier.armoire ON DELETE CASCADE,
    numero     text NOT NULL,
    UNIQUE (armoire_id, numero)
);
COMMENT ON TABLE metier.depart IS 'Départ d''une armoire (circuit). Publié seulement par Nantes Métropole.';

CREATE TABLE metier.support (
    id                    bigserial PRIMARY KEY,
    gestionnaire_id       smallint NOT NULL REFERENCES metier.gestionnaire,
    code                  text NOT NULL,
    insee                 char(5) NOT NULL REFERENCES ref.commune,
    armoire_id            integer REFERENCES metier.armoire,
    voie                  text,
    quartier              text,
    type_support          varchar(3) NOT NULL DEFAULT 'XX' REFERENCES ref.support_luminaire,
    hauteur_m             numeric(5,2) CHECK (hauteur_m > 0 AND hauteur_m <= 60),
    saillie_m             numeric(4,2) CHECK (saillie_m >= 0),
    nature                text,
    forme                 text,
    couleur               text,
    marque                text,
    etat                  text REFERENCES ref.etat_support,
    type_pose             text REFERENCES ref.type_pose,
    type_massif           text REFERENCES ref.type_massif,
    dimension_massif      text,
    entraxe               text,
    presence_terre        boolean,
    prise_illumination    boolean,
    autonome              boolean,
    date_pose             date CHECK (date_pose >= DATE '1900-01-01'),
    proprietaire          text REFERENCES ref.proprietaire,
    competence_transferee boolean,
    type_maintenance      text,
    exploitant            text,
    classe_precision      char(1) REFERENCES ref.classe_precision,
    z_m                   numeric(7,2),
    observation           text,
    geom                  geometry(Point, 2154) NOT NULL,
    lot_id                integer NOT NULL REFERENCES flux.lot,
    ligne_source          integer,
    retire_le             date,
    maj_locale            boolean NOT NULL DEFAULT false,
    UNIQUE (gestionnaire_id, code)
);
COMMENT ON TABLE metier.support IS 'Mât, poteau, façade ou borne : ce qui porte un ou plusieurs points lumineux.';
COMMENT ON COLUMN metier.support.retire_le IS 'Date de la collecte où l''objet a disparu de la source. L''objet est conservé, jamais supprimé.';
CREATE INDEX support_geom ON metier.support USING gist (geom);
CREATE INDEX support_insee ON metier.support (insee);
CREATE INDEX support_armoire ON metier.support (armoire_id);

-- Format horaire de la section 3.5 du géostandard : 21:36HL, 20:36TU, -196MN, -15CS, +15LS
CREATE FUNCTION ref.heure_eclext_valide(h text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT h ~ '^(([01][0-9]|2[0-3]):[0-5][0-9](HL|TU)|[+-]?[0-9]+(MN|CS|LS))$'
$$;

CREATE TABLE metier.profil_nocturne (
    nom_profil       text PRIMARY KEY,
    allumage_soir    text CHECK (ref.heure_eclext_valide(allumage_soir)),
    extinction_matin text CHECK (ref.heure_eclext_valide(extinction_matin))
);

CREATE TABLE metier.plage_variation (
    nom_plage          text PRIMARY KEY,
    grandeur_variation varchar(2) NOT NULL REFERENCES ref.grandeur_variation,
    heure_debut        text NOT NULL CHECK (ref.heure_eclext_valide(heure_debut)),
    heure_fin          text NOT NULL CHECK (ref.heure_eclext_valide(heure_fin)),
    format_variation   varchar(2) REFERENCES ref.format_variation,
    valeur             numeric,
    valide_de          date,
    valide_jusque      date,
    CHECK (valide_jusque IS NULL OR valide_de IS NULL OR valide_jusque > valide_de),
    CHECK (grandeur_variation <> 'EX' OR (format_variation IS NULL AND valeur IS NULL)),
    CHECK (format_variation <> '%' OR valeur BETWEEN 0 AND 100)
);

CREATE TABLE metier.profil_contient_plage (
    nom_profil text NOT NULL REFERENCES metier.profil_nocturne ON DELETE CASCADE,
    nom_plage  text NOT NULL REFERENCES metier.plage_variation ON DELETE CASCADE,
    PRIMARY KEY (nom_profil, nom_plage)
);

CREATE TABLE metier.point_lumineux (
    id                         bigserial PRIMARY KEY,
    gestionnaire_id            smallint NOT NULL REFERENCES metier.gestionnaire,
    code                       text NOT NULL,
    support_id                 bigint NOT NULL REFERENCES metier.support,
    depart_id                  integer REFERENCES metier.depart,
    insee                      char(5) NOT NULL REFERENCES ref.commune,
    -- Attributs obligatoires d'EclExt. Les listes acceptent XX (inconnu) ; pour les autres, NULL
    -- dit que la source ne le publie pas : le contrôle de conformité le compte, personne ne l'invente.
    statut                     text NOT NULL DEFAULT 'functional' REFERENCES ref.statut_installation,
    eclairage_public           boolean,
    usage                      varchar(2) NOT NULL DEFAULT 'XX' REFERENCES ref.usage,
    type_source                varchar(5) NOT NULL DEFAULT 'XX' REFERENCES ref.type_source,
    structure                  varchar(4) NOT NULL DEFAULT 'XX' REFERENCES ref.structure_luminaire,
    temperature_couleur        integer CHECK (temperature_couleur BETWEEN 1000 AND 10000),
    puissance_w                numeric(7,1) CHECK (puissance_w > 0),
    valide_de                  date,
    extinction_nuit            boolean,
    est_adaptatif              boolean,
    -- Attributs optionnels
    fabricant                  text,
    modele                     text,
    photometrie                text,
    hauteur_feu_m              numeric(5,2) CHECK (hauteur_feu_m > 0 AND hauteur_feu_m <= 60),
    flux_source_lm             numeric(9,1) CHECK (flux_source_lm > 0),
    flux_luminaire_lm          numeric(9,1) CHECK (flux_luminaire_lm > 0),
    cie3                       numeric(4,3) CHECK (cie3 BETWEEN 0 AND 1),
    ulr_nominal                numeric(4,3) CHECK (ulr_nominal BETWEEN 0 AND 1),
    ulr_installe               numeric(4,3) CHECK (ulr_installe BETWEEN 0 AND 1),
    inclinaison_max            numeric(5,2) CHECK (inclinaison_max BETWEEN 0 AND 360),
    inclinaison_installee      numeric(5,2) CHECK (inclinaison_installee BETWEEN 0 AND 360),
    valide_jusque              date,
    date_premiere_installation date,
    profil_nocturne            text REFERENCES metier.profil_nocturne,
    eclairage_adaptatif        varchar(2) REFERENCES ref.eclairage_adaptatif,
    -- Compléments internes
    nb_sources                 smallint NOT NULL DEFAULT 1 CHECK (nb_sources > 0),
    designation_lampe          text,
    un_point_par_support       boolean NOT NULL DEFAULT false,
    maj_locale                 boolean NOT NULL DEFAULT false,
    geom                       geometry(Point, 2154) NOT NULL,
    lot_id                     integer NOT NULL REFERENCES flux.lot,
    ligne_source               integer,
    retire_le                  date,
    UNIQUE (gestionnaire_id, code),
    CHECK (valide_jusque IS NULL OR valide_de IS NULL OR valide_jusque > valide_de),
    CHECK (date_premiere_installation IS NULL OR valide_de IS NULL OR valide_de >= date_premiere_installation),
    CHECK (eclairage_adaptatif IS NULL OR est_adaptatif IS NOT FALSE)
);
COMMENT ON TABLE metier.point_lumineux IS 'Ensemble luminaire et source(s) géolocalisé, au sens du géostandard.';
COMMENT ON COLUMN metier.point_lumineux.un_point_par_support IS 'Vrai si la source publie les supports seulement : un point est créé par support, sans connaître le nombre réel de luminaires.';
COMMENT ON COLUMN metier.point_lumineux.maj_locale IS 'Vrai après une correction ou une intervention : la prochaine collecte n''écrase pas ce point. Rempli par un déclencheur (sql/40_exploitation.sql), comme sur les supports et les armoires.';
CREATE INDEX point_geom ON metier.point_lumineux USING gist (geom);
CREATE INDEX point_support ON metier.point_lumineux (support_id);
CREATE INDEX point_insee ON metier.point_lumineux (insee);
CREATE INDEX point_type_source ON metier.point_lumineux (type_source);

-- Lignes écartées par la reprise, avec le motif : aucune ligne source ne disparaît sans trace
CREATE TABLE controle.rejet (
    lot_id  integer NOT NULL REFERENCES flux.lot,
    ligne   integer NOT NULL,
    motif   text NOT NULL,
    contenu jsonb,
    PRIMARY KEY (lot_id, ligne)
);
