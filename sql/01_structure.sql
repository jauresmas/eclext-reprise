-- Schémas de la base et suivi des lots collectés.
--
--   src          données brutes, toutes en texte, jamais modifiées
--   flux         lots collectés et différentiel entre deux lots
--   ref          listes de valeurs EclExt, nomenclatures internes, correspondances, communes
--   metier       base structurée : armoire, départ, support, point lumineux
--   exploitation signalements et interventions
--   eclext       vues au format d'échange du géostandard
--   controle     règles de contrôle, écarts, bilans
--   admin        habilitations et périmètres
--   audit        journal des modifications

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE SCHEMA IF NOT EXISTS src;
CREATE SCHEMA IF NOT EXISTS flux;
CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS metier;
CREATE SCHEMA IF NOT EXISTS exploitation;
CREATE SCHEMA IF NOT EXISTS eclext;
CREATE SCHEMA IF NOT EXISTS controle;
CREATE SCHEMA IF NOT EXISTS admin;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE flux.lot (
    id            serial PRIMARY KEY,
    source        text NOT NULL,
    date_collecte text NOT NULL,
    url           text NOT NULL,
    page          text,
    licence       text,
    sha256        text NOT NULL,
    taille        bigint NOT NULL,
    nb_lignes     integer NOT NULL,
    courant       boolean NOT NULL DEFAULT false,
    charge_le     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, sha256)
);
COMMENT ON TABLE flux.lot IS 'Une ligne par fichier collecté : adresse, date, empreinte. Un seul lot courant par source.';

CREATE UNIQUE INDEX lot_courant_unique ON flux.lot (source) WHERE courant;

CREATE TABLE flux.ecart_lot (
    source      text NOT NULL,
    lot_avant   integer NOT NULL REFERENCES flux.lot(id),
    lot_apres   integer NOT NULL REFERENCES flux.lot(id),
    cle         text NOT NULL,
    nature      text NOT NULL CHECK (nature IN ('ajout', 'retrait', 'modification')),
    champs      text[],
    PRIMARY KEY (lot_avant, lot_apres, cle)
);
COMMENT ON TABLE flux.ecart_lot IS 'Différentiel entre deux collectes successives d''une même source.';

-- Compare le lot courant d'une source au lot précédent, ligne à ligne, sur une clé.
CREATE FUNCTION flux.comparer_lots(p_source text, p_cle text[]) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    v_apres integer;
    v_avant integer;
    v_cle   text;
    v_n     integer;
BEGIN
    SELECT id INTO v_apres FROM flux.lot WHERE source = p_source AND courant;
    SELECT max(id) INTO v_avant FROM flux.lot WHERE source = p_source AND id < v_apres;
    IF v_avant IS NULL THEN
        RETURN 0;  -- premier lot : rien à comparer
    END IF;
    SELECT string_agg(format('coalesce(t.%I::text, %L)', c, ''), ' || ''|'' || ') INTO v_cle FROM unnest(p_cle) c;
    EXECUTE format($q$
        WITH avant AS (
            SELECT %1$s AS cle, to_jsonb(t) - 'lot_id' - 'ligne' AS j FROM src.%2$I t WHERE t.lot_id = %3$s
        ), apres AS (
            SELECT %1$s AS cle, to_jsonb(t) - 'lot_id' - 'ligne' AS j FROM src.%2$I t WHERE t.lot_id = %4$s
        )
        INSERT INTO flux.ecart_lot (source, lot_avant, lot_apres, cle, nature, champs)
        SELECT %5$L, %3$s, %4$s, coalesce(a.cle, b.cle),
               CASE WHEN a.cle IS NULL THEN 'ajout' WHEN b.cle IS NULL THEN 'retrait' ELSE 'modification' END,
               CASE WHEN a.cle IS NOT NULL AND b.cle IS NOT NULL THEN
                   ARRAY(SELECT k FROM jsonb_each(a.j) e(k, v) WHERE (b.j -> k) IS DISTINCT FROM v)
               END
        FROM avant a FULL JOIN apres b USING (cle)
        WHERE a.cle IS NULL OR b.cle IS NULL OR a.j IS DISTINCT FROM b.j
    $q$, v_cle, p_source, v_avant, v_apres, p_source);
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$;
COMMENT ON FUNCTION flux.comparer_lots IS 'Écrit dans flux.ecart_lot les ajouts, retraits et modifications entre les deux derniers lots.';
