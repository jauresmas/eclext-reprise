-- Comptes et périmètres. Trois profils de travail, plus l'administration :
--
--   ep_administrateur  structure et données, tout le territoire
--   ep_collectivite    consulte le patrimoine de ses communes, y déclare des signalements
--   ep_entreprise      consulte le patrimoine de son périmètre, tient à jour SES interventions
--   ep_lecture         lit le format d'échange EclExt, rien d'autre
--
-- Le périmètre n'est pas un filtre d'application : il est appliqué par la base (sécurité au niveau
-- des lignes), donc identique quel que soit l'outil de connexion, QGIS, DBeaver ou autre.

DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['ep_administrateur', 'ep_collectivite', 'ep_entreprise', 'ep_lecture'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', r);
        END IF;
    END LOOP;
END $$;

CREATE TABLE admin.habilitation (
    login         text PRIMARY KEY,
    profil        text NOT NULL CHECK (profil IN ('ep_administrateur', 'ep_collectivite', 'ep_entreprise', 'ep_lecture')),
    communes      char(5)[] NOT NULL DEFAULT '{}',
    entreprise_id smallint REFERENCES admin.entreprise,
    CHECK (profil <> 'ep_entreprise' OR entreprise_id IS NOT NULL)
);
COMMENT ON TABLE admin.habilitation IS 'Un compte, un profil, un périmètre de communes. Créer un compte : voir admin.creer_compte.';

CREATE FUNCTION admin.mes_communes() RETURNS char(5)[]
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT coalesce((SELECT communes FROM admin.habilitation WHERE login = session_user), '{}')
$$;

CREATE FUNCTION admin.mon_entreprise() RETURNS smallint
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT entreprise_id FROM admin.habilitation WHERE login = session_user
$$;

-- Création d'un compte en une ligne. Le mot de passe se règle à part, par l'administrateur du serveur.
CREATE FUNCTION admin.creer_compte(p_login text, p_profil text, p_communes char(5)[] DEFAULT '{}', p_entreprise smallint DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = p_login) THEN
        EXECUTE format('CREATE ROLE %I LOGIN IN ROLE %I', p_login, p_profil);
    ELSE
        EXECUTE format('GRANT %I TO %I', p_profil, p_login);
    END IF;
    INSERT INTO admin.habilitation (login, profil, communes, entreprise_id)
    VALUES (p_login, p_profil, p_communes, p_entreprise)
    ON CONFLICT (login) DO UPDATE SET profil = EXCLUDED.profil, communes = EXCLUDED.communes, entreprise_id = EXCLUDED.entreprise_id;
END;
$$;
REVOKE EXECUTE ON FUNCTION admin.creer_compte(text, text, char(5)[], smallint) FROM PUBLIC;

-- Droits sur les schémas et les tables ---------------------------------------------------------
GRANT USAGE ON SCHEMA ref, eclext TO ep_administrateur, ep_collectivite, ep_entreprise, ep_lecture;
GRANT USAGE ON SCHEMA metier, exploitation, controle TO ep_administrateur, ep_collectivite, ep_entreprise;
GRANT USAGE ON SCHEMA admin TO ep_administrateur, ep_collectivite, ep_entreprise;
GRANT USAGE ON SCHEMA audit, flux TO ep_administrateur;
GRANT USAGE ON SCHEMA public TO ep_administrateur, ep_collectivite, ep_entreprise, ep_lecture;
GRANT SELECT ON spatial_ref_sys, geometry_columns TO ep_administrateur, ep_collectivite, ep_entreprise, ep_lecture;

GRANT SELECT ON ALL TABLES IN SCHEMA ref TO ep_administrateur, ep_collectivite, ep_entreprise, ep_lecture;
GRANT SELECT ON ALL TABLES IN SCHEMA eclext TO ep_administrateur, ep_collectivite, ep_entreprise, ep_lecture;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ref, eclext TO ep_administrateur, ep_collectivite, ep_entreprise, ep_lecture;
GRANT EXECUTE ON FUNCTION admin.mes_communes(), admin.mon_entreprise() TO ep_administrateur, ep_collectivite, ep_entreprise;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA metier, exploitation TO ep_administrateur;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA controle TO ep_administrateur;
GRANT SELECT ON ALL TABLES IN SCHEMA audit, flux TO ep_administrateur;
GRANT SELECT, INSERT, UPDATE, DELETE ON admin.habilitation, admin.entreprise TO ep_administrateur;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA metier, exploitation, controle, admin TO ep_administrateur;

GRANT SELECT ON ALL TABLES IN SCHEMA metier TO ep_collectivite, ep_entreprise;
GRANT SELECT ON admin.entreprise TO ep_collectivite, ep_entreprise;
GRANT SELECT ON controle.regle, controle.ecart TO ep_collectivite, ep_entreprise;

GRANT SELECT, INSERT ON exploitation.signalement TO ep_collectivite;
GRANT USAGE ON SEQUENCE exploitation.signalement_id_seq TO ep_collectivite;
GRANT SELECT ON exploitation.intervention TO ep_collectivite;
REVOKE EXECUTE ON FUNCTION exploitation.importer_signalements_terrain(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION exploitation.importer_signalements_terrain(jsonb) TO ep_administrateur, ep_collectivite;

GRANT SELECT ON exploitation.signalement TO ep_entreprise;
GRANT SELECT ON exploitation.intervention TO ep_entreprise;
-- L'entreprise ne change ni l'objet, ni la nature, ni le titulaire de l'intervention
GRANT UPDATE (etat, date_prevue, date_realisee, compte_rendu, nouveau_type_source, nouvelle_puissance_w, nouvelle_temperature)
    ON exploitation.intervention TO ep_entreprise;

-- Sécurité au niveau des lignes ----------------------------------------------------------------
-- Les vues eclext appartiennent au propriétaire de la base : elles donnent le format d'échange complet,
-- comme les fichiers publiés. Les tables, elles, ne montrent que le périmètre du compte.
ALTER TABLE metier.armoire ENABLE ROW LEVEL SECURITY;
ALTER TABLE metier.support ENABLE ROW LEVEL SECURITY;
ALTER TABLE metier.point_lumineux ENABLE ROW LEVEL SECURITY;
ALTER TABLE exploitation.signalement ENABLE ROW LEVEL SECURITY;
ALTER TABLE exploitation.intervention ENABLE ROW LEVEL SECURITY;
ALTER TABLE controle.ecart ENABLE ROW LEVEL SECURITY;

CREATE POLICY administrateur ON metier.armoire TO ep_administrateur USING (true) WITH CHECK (true);
CREATE POLICY administrateur ON metier.support TO ep_administrateur USING (true) WITH CHECK (true);
CREATE POLICY administrateur ON metier.point_lumineux TO ep_administrateur USING (true) WITH CHECK (true);
CREATE POLICY administrateur ON exploitation.signalement TO ep_administrateur USING (true) WITH CHECK (true);
CREATE POLICY administrateur ON exploitation.intervention TO ep_administrateur USING (true) WITH CHECK (true);
CREATE POLICY administrateur ON controle.ecart TO ep_administrateur USING (true) WITH CHECK (true);

CREATE POLICY perimetre ON metier.armoire FOR SELECT TO ep_collectivite, ep_entreprise USING (insee = ANY (admin.mes_communes()));
CREATE POLICY perimetre ON metier.support FOR SELECT TO ep_collectivite, ep_entreprise USING (insee = ANY (admin.mes_communes()));
CREATE POLICY perimetre ON metier.point_lumineux FOR SELECT TO ep_collectivite, ep_entreprise USING (insee = ANY (admin.mes_communes()));
CREATE POLICY perimetre ON controle.ecart FOR SELECT TO ep_collectivite, ep_entreprise USING (insee = ANY (admin.mes_communes()));
CREATE POLICY perimetre ON exploitation.signalement FOR SELECT TO ep_collectivite, ep_entreprise USING (insee = ANY (admin.mes_communes()));
CREATE POLICY declarer ON exploitation.signalement FOR INSERT TO ep_collectivite WITH CHECK (insee = ANY (admin.mes_communes()));

CREATE POLICY perimetre ON exploitation.intervention FOR SELECT TO ep_collectivite USING (insee = ANY (admin.mes_communes()));
CREATE POLICY les_siennes ON exploitation.intervention FOR SELECT TO ep_entreprise USING (entreprise_id = admin.mon_entreprise());
CREATE POLICY les_siennes_maj ON exploitation.intervention FOR UPDATE TO ep_entreprise
    USING (entreprise_id = admin.mon_entreprise()) WITH CHECK (entreprise_id = admin.mon_entreprise());

-- Comptes de démonstration, sans mot de passe : l'instance n'écoute que sur la machine locale ---
SELECT admin.creer_compte('demo_admin', 'ep_administrateur');
SELECT admin.creer_compte('demo_lecture', 'ep_lecture');
