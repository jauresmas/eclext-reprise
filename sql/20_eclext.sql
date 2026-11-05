-- Vues au format d'échange du géostandard EclExt (CNIG, v1.1).
-- Noms de classes et d'attributs du standard, dates sur 8 caractères (AAAAMMJJ, section 4.4),
-- chaînes limitées aux caractères admis par la section 4.4. Les objets retirés de la source
-- n'y figurent pas.

-- Section 4.4 : minuscules et majuscules sans accent, chiffres, trait d'union, souligné, point
CREATE FUNCTION eclext.chaine(texte text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT nullif(trim(BOTH '_' FROM regexp_replace(unaccent(texte), '[^A-Za-z0-9._-]+', '_', 'g')), '')
$$;

CREATE VIEW eclext.pointlumineux AS
SELECT p.id,
       g.code                                       AS gestionnaire,
       eclext.chaine(p.code)                        AS identifiant,
       p.statut,
       p.eclairage_public                           AS "eclairagePublic",
       p.usage,
       p.type_source                                AS "typeSource",
       p.structure,
       s.type_support                               AS support,
       p.temperature_couleur                        AS "temperatureCouleur",
       p.puissance_w                                AS puissance,
       eclext.chaine(p.fabricant)                   AS fabricant,
       eclext.chaine(p.modele)                      AS modele,
       eclext.chaine(p.photometrie)                 AS photometrie,
       p.hauteur_feu_m                              AS "hauteurFeu",
       p.flux_source_lm                             AS "fluxSource",
       p.flux_luminaire_lm                          AS "fluxLuminaire",
       p.cie3,
       p.ulr_nominal                                AS "ulrNominal",
       p.ulr_installe                               AS "ulrInstalle",
       p.inclinaison_max                            AS "inclinaisonMax",
       p.inclinaison_installee                      AS "inclinaisonInstallee",
       to_char(p.valide_de, 'YYYYMMDD')             AS "valideDe",
       to_char(p.valide_jusque, 'YYYYMMDD')         AS "valideJusque",
       to_char(p.date_premiere_installation, 'YYYYMMDD') AS "datePremiereInstallation",
       p.extinction_nuit                            AS "extinctionNuit",
       eclext.chaine(p.profil_nocturne)             AS "profilNocturne",
       p.est_adaptatif                              AS "estAdaptatif",
       p.eclairage_adaptatif                        AS "eclairageAdaptatif",
       p.geom                                       AS geometrie
FROM metier.point_lumineux p
JOIN metier.support s ON s.id = p.support_id
JOIN metier.gestionnaire g ON g.id = p.gestionnaire_id
WHERE p.retire_le IS NULL;
COMMENT ON VIEW eclext.pointlumineux IS 'Classe PointLumineux du géostandard. Les colonnes gestionnaire et id sont des compléments d''export, retirés des fichiers livrés sauf l''identifiant.';

CREATE VIEW eclext.profilnocturne AS
SELECT eclext.chaine(nom_profil) AS "nomProfil", allumage_soir AS "allumageSoir", extinction_matin AS "extinctionMatin"
FROM metier.profil_nocturne;

CREATE VIEW eclext.plagevariation AS
SELECT eclext.chaine(nom_plage) AS "nomPlage", grandeur_variation AS "grandeurVariation", heure_debut AS "heureDebut",
       heure_fin AS "heureFin", format_variation AS "formatVariation", valeur,
       to_char(valide_de, 'YYYYMMDD') AS "valideDe", to_char(valide_jusque, 'YYYYMMDD') AS "valideJusque"
FROM metier.plage_variation;

CREATE VIEW eclext.profilcontientplage AS
SELECT eclext.chaine(nom_profil) AS "nomProfil", eclext.chaine(nom_plage) AS "nomPlage"
FROM metier.profil_contient_plage;
