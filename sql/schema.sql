-- ============================================================================
-- Analytical warehouse schema (star schema) for the DVF real estate platform.
-- Loaded automatically by the postgres-dwh container on first start.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS dwh;

-- ----------------------------------------------------------------------------
-- Dimension: commune (French municipality)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.dim_commune (
    commune_key      SERIAL PRIMARY KEY,
    insee_code       VARCHAR(5) NOT NULL UNIQUE,
    commune_name     VARCHAR(150) NOT NULL,
    department_code  VARCHAR(3) NOT NULL,
    department_name  VARCHAR(100),
    region_name      VARCHAR(100),
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION
);

-- ----------------------------------------------------------------------------
-- Dimension: property type (house, apartment, land, etc.)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.dim_property_type (
    property_type_key SERIAL PRIMARY KEY,
    property_type_code VARCHAR(10) NOT NULL UNIQUE,
    property_type_label VARCHAR(50) NOT NULL
);

-- ----------------------------------------------------------------------------
-- Dimension: date (one row per calendar day present in the dataset)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.dim_date (
    date_key     INT PRIMARY KEY,        -- YYYYMMDD
    full_date    DATE NOT NULL,
    year         SMALLINT NOT NULL,
    quarter      SMALLINT NOT NULL,
    month        SMALLINT NOT NULL,
    month_name   VARCHAR(20) NOT NULL,
    day_of_week  SMALLINT NOT NULL
);

-- ----------------------------------------------------------------------------
-- Fact: individual real estate transactions (one row per mutation/lot)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.fact_transactions (
    transaction_key     BIGSERIAL PRIMARY KEY,
    source_id           VARCHAR(64) NOT NULL,      -- id_mutation from the raw DVF file
    commune_key          INT NOT NULL REFERENCES dwh.dim_commune(commune_key),
    property_type_key    INT NOT NULL REFERENCES dwh.dim_property_type(property_type_key),
    date_key              INT NOT NULL REFERENCES dwh.dim_date(date_key),
    sale_price            NUMERIC(14, 2) NOT NULL,
    surface_real_bati     NUMERIC(10, 2),          -- built surface area (m2)
    surface_terrain        NUMERIC(10, 2),          -- land surface area (m2)
    nb_rooms                SMALLINT,
    price_per_sqm           NUMERIC(12, 2),
    is_outlier               BOOLEAN DEFAULT FALSE,   -- flagged by the anomaly detection job
    loaded_at                TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (source_id, commune_key, property_type_key)
);

CREATE INDEX IF NOT EXISTS idx_fact_transactions_commune
    ON dwh.fact_transactions (commune_key);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_date
    ON dwh.fact_transactions (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_transactions_property_type
    ON dwh.fact_transactions (property_type_key);

-- ----------------------------------------------------------------------------
-- Seed the property type dimension with the DVF nomenclature.
-- ----------------------------------------------------------------------------
INSERT INTO dwh.dim_property_type (property_type_code, property_type_label) VALUES
    ('1', 'Maison'),
    ('2', 'Appartement'),
    ('3', 'Dependance'),
    ('4', 'Local industriel, commercial ou assimile')
ON CONFLICT (property_type_code) DO NOTHING;
