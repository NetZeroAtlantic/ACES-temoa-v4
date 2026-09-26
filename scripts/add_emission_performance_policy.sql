-- Add generic emissions-performance policy tables to an existing Temoa v4 database.
-- Run this script once against databases created before these tables were added.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS emission_performance_standard
(
    policy      TEXT    NOT NULL,
    region      TEXT    NOT NULL REFERENCES region (region),
    period      INTEGER NOT NULL REFERENCES time_period (period),
    emis_comm   TEXT    NOT NULL REFERENCES commodity (name),
    intensity   REAL    NOT NULL CHECK (intensity >= 0),
    units       TEXT,
    notes       TEXT,
    PRIMARY KEY (policy, region, period, emis_comm)
);

CREATE TABLE IF NOT EXISTS policy_technology
(
    policy      TEXT NOT NULL,
    region      TEXT NOT NULL REFERENCES region (region),
    tech        TEXT NOT NULL REFERENCES technology (tech),
    output_comm TEXT NOT NULL REFERENCES commodity (name),
    notes       TEXT,
    PRIMARY KEY (policy, region, tech, output_comm)
);

CREATE TABLE IF NOT EXISTS policy_emission_link
(
    policy             TEXT NOT NULL,
    region             TEXT NOT NULL REFERENCES region (region),
    tech               TEXT NOT NULL REFERENCES technology (tech),
    output_comm        TEXT NOT NULL REFERENCES commodity (name),
    linked_tech        TEXT NOT NULL REFERENCES technology (tech),
    linked_output_comm TEXT NOT NULL REFERENCES commodity (name),
    allocation         REAL NOT NULL DEFAULT 1.0
        CHECK (allocation > 0 AND allocation <= 1),
    notes              TEXT,
    PRIMARY KEY (
        policy, region, tech, output_comm, linked_tech, linked_output_comm
    )
);

-- Example only; replace names and values with those used by the target database.
-- INSERT INTO emission_performance_standard
--     (policy, region, period, emis_comm, intensity, units)
-- VALUES ('CER', 'NB', 2035, 'CO2', 8.333333333, 'kt/PJ'); -- 30 t/GWh
--
-- INSERT INTO policy_technology
--     (policy, region, tech, output_comm)
-- VALUES ('CER', 'NB', 'E_NGACC-CCS', 'ELCG');
--
-- Upstream gas-supply factor. Because E_NG is an input to E_NGACC-CCS, Temoa
-- applies this linked rate to that generator's fuel use.
-- INSERT INTO policy_emission_link
--     (policy, region, tech, output_comm, linked_tech, linked_output_comm)
-- VALUES ('CER', 'NB', 'E_NGACC-CCS', 'ELCG', 'IMP_NG_ELC', 'E_NG');
--
-- The current Joint Atlantic database stores captured CO2 as a negative
-- emission_activity on E_NGACC-CCS/ELCG. Direct emissions are included
-- automatically, so it does not need a downstream policy link.
