-- Add absolute seasonal output-activity limits to a Temoa v4 database.
CREATE TABLE IF NOT EXISTS limit_seasonal_activity
(
    region        TEXT NOT NULL REFERENCES region (region),
    period        INTEGER NOT NULL REFERENCES time_period (period),
    season        TEXT NOT NULL REFERENCES time_season (season),
    tech_or_group TEXT NOT NULL,
    output_comm   TEXT NOT NULL REFERENCES commodity (name),
    operator      TEXT NOT NULL DEFAULT 'le' REFERENCES operator (operator),
    daily_limit   REAL NOT NULL CHECK (daily_limit >= 0),
    units         TEXT,
    notes         TEXT,
    PRIMARY KEY (region, period, season, tech_or_group, output_comm, operator)
);

-- Example: cap IMP_NG_ELC output E_NG at an average of 0.481 PJ/day
-- during season S1 in 2035. Replace S1 with the desired database season.
-- INSERT INTO limit_seasonal_activity
--     (region, period, season, tech_or_group, output_comm,
--      operator, daily_limit, units, notes)
-- VALUES
--     ('NB', 2035, 'S1', 'IMP_NG_ELC', 'E_NG',
--      'le', 0.481, 'PJ/day', 'Daily natural-gas availability limit');
