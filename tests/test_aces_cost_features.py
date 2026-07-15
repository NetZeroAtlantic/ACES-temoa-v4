"""Regression tests for ACES cost features ported to the v4 model."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from temoa._internal.temoa_sequencer import TemoaSequencer
from temoa.components import costs, emissions
from temoa.core.config import TemoaConfig
from temoa.model_checking import network_model_data

TEST_ROOT = Path(__file__).parent
SCHEMA = TEST_ROOT.parent / 'temoa' / 'db_schema' / 'temoa_schema_v4.sql'
EMISSIONS_DATA = TEST_ROOT / 'testing_data' / 'emissions.sql'


def _build_feature_database(tmp_path: Path, name: str, extra_sql: str = '') -> Path:
    db_path = tmp_path / f'{name}.sqlite'
    with contextlib.closing(sqlite3.connect(db_path)) as con:
        con.execute('PRAGMA foreign_keys = OFF')
        con.executescript(SCHEMA.read_text(encoding='utf-8'))
        con.execute('PRAGMA foreign_keys = OFF')
        con.executescript(EMISSIONS_DATA.read_text(encoding='utf-8'))
        if extra_sql:
            con.executescript(extra_sql)
        con.commit()
    return db_path


def _run_feature_model(db_path: Path, tmp_path: Path) -> TemoaSequencer:
    config = TemoaConfig(
        scenario='aces feature test',
        scenario_mode='perfect_foresight',
        input_database=db_path,
        output_database=db_path,
        output_path=tmp_path,
        solver_name='appsi_highs',
        time_sequencing='seasonal_timeslices',
        reserve_margin='static',
        silent=True,
        price_check=False,
        output_threshold_cost=1e-9,
    )
    sequencer = TemoaSequencer(config=config)
    sequencer.start()
    return sequencer


def test_cost_variable_multiplier_weights_slices_and_defaults_missing_rows(
    tmp_path: Path,
) -> None:
    db_path = _build_feature_database(
        tmp_path,
        'variable_multiplier',
        """
        INSERT INTO cost_variable
        VALUES ('Testregion', 2000, 'TechOrdinary', 2000, 10.0, NULL, NULL);
        INSERT INTO cost_variable_multiplier
        VALUES ('Testregion', 'TechOrdinary', 'S1', 'TOD1', 2.0, NULL);
        """,
    )

    _run_feature_model(db_path, tmp_path)

    with contextlib.closing(sqlite3.connect(db_path)) as con:
        flow_rows = con.execute(
            """
            SELECT tod, flow
            FROM output_flow_out
            WHERE scenario = 'aces feature test'
              AND period = 2000
              AND tech = 'TechOrdinary'
            """
        ).fetchall()
        reported_cost = con.execute(
            """
            SELECT var
            FROM output_cost
            WHERE scenario = 'aces feature test'
              AND period = 2000
              AND tech = 'TechOrdinary'
              AND vintage = 2000
            """
        ).fetchone()[0]

    weighted_activity = sum(flow * (2.0 if tod == 'TOD1' else 1.0) for tod, flow in flow_rows)
    assert reported_cost == pytest.approx(weighted_activity * 10.0 * 5.0)
    assert {tod for tod, _flow in flow_rows} == {'TOD1', 'TOD2'}


def test_cost_variable_multiplier_rejects_annual_technology(tmp_path: Path) -> None:
    db_path = _build_feature_database(
        tmp_path,
        'annual_multiplier',
        """
        INSERT INTO cost_variable_multiplier
        VALUES ('Testregion', 'TechAnnual', 'S1', 'TOD1', 2.0, NULL);
        """,
    )

    with pytest.raises((ValueError, RuntimeError), match='cost_variable_multiplier'):
        _run_feature_model(db_path, tmp_path)


def test_negative_effective_variable_cost_is_marked_for_cycle_checks(tmp_path: Path) -> None:
    db_path = _build_feature_database(
        tmp_path,
        'negative_multiplier',
        """
        INSERT INTO cost_variable
        VALUES ('Testregion', 2000, 'TechOrdinary', 2000, 10.0, NULL, NULL);
        INSERT INTO cost_variable_multiplier
        VALUES ('Testregion', 'TechOrdinary', 'S1', 'TOD1', -1.0, NULL);
        """,
    )

    with contextlib.closing(sqlite3.connect(db_path)) as con:
        lookup = network_model_data._fetch_lookup_data(con.cursor())

    assert 'TechOrdinary' in lookup['neg_cost_techs']


def test_exchange_region_emissions_are_indexed() -> None:
    model = SimpleNamespace(
        efficiency=SimpleNamespace(
            sparse_keys=lambda: {('R_EXP-NB', 'ELC', 'E_TRANS-QC', 1900, 'ELCG-RPS')}
        ),
        commodity_emissions={'CO2e-Imports-Tax'},
        regional_indices={'NB', 'R_EXP', 'R_EXP-NB'},
    )

    assert emissions.emission_activity_indices(model) == {
        ('R_EXP-NB', 'CO2e-Imports-Tax', 'ELC', 'E_TRANS-QC', 1900, 'ELCG-RPS')
    }


def test_output_based_standard_credits_do_not_change_physical_emissions(tmp_path: Path) -> None:
    baseline_db_path = _build_feature_database(tmp_path, 'output_based_standard_baseline')
    _run_feature_model(baseline_db_path, tmp_path)
    with contextlib.closing(sqlite3.connect(baseline_db_path)) as con:
        baseline_physical_emissions = dict(
            con.execute(
                """
                SELECT tech, SUM(emission)
                FROM output_emission
                WHERE scenario = 'aces feature test'
                  AND period = 2000
                  AND tech IN ('TechOrdinary', 'TechAnnual')
                GROUP BY tech
                """
            ).fetchall()
        )
        baseline_objective = con.execute(
            """
            SELECT total_system_cost
            FROM output_objective
            WHERE scenario = 'aces feature test'
            """
        ).fetchone()[0]

    db_path = _build_feature_database(
        tmp_path,
        'output_based_standard',
        """
        INSERT INTO output_based_standard
        VALUES (
            'Testregion', 2000, 'emission', 'ordinary_in', 'TechOrdinary',
            'ordinary_out', 0.4, NULL, NULL
        );
        INSERT INTO output_based_standard
        VALUES (
            'Testregion', 2000, 'emission', 'annual_in', 'TechAnnual',
            'annual_out', 0.2, NULL, NULL
        );
        """,
    )

    _run_feature_model(db_path, tmp_path)

    with contextlib.closing(sqlite3.connect(db_path)) as con:
        physical_emissions = dict(
            con.execute(
                """
                SELECT tech, SUM(emission)
                FROM output_emission
                WHERE scenario = 'aces feature test'
                  AND period = 2000
                  AND tech IN ('TechOrdinary', 'TechAnnual')
                GROUP BY tech
                """
            ).fetchall()
        )
        cost_rows = {
            tech: (emiss, d_emiss, obps, d_obps)
            for tech, emiss, d_emiss, obps, d_obps in con.execute(
                """
                SELECT tech, emiss, d_emiss, obps, d_obps
                FROM output_cost
                WHERE scenario = 'aces feature test'
                  AND period = 2000
                  AND tech IN ('TechOrdinary', 'TechAnnual')
                """
            ).fetchall()
        }
        reported_obps_total = con.execute(
            """
            SELECT SUM(COALESCE(d_obps, 0))
            FROM output_cost
            WHERE scenario = 'aces feature test'
            """
        ).fetchone()[0]
        objective = con.execute(
            """
            SELECT total_system_cost
            FROM output_objective
            WHERE scenario = 'aces feature test'
            """
        ).fetchone()[0]

    expected_physical_emissions = {'TechOrdinary': 0.3, 'TechAnnual': 1.0}
    assert baseline_physical_emissions == pytest.approx(expected_physical_emissions)
    assert physical_emissions == pytest.approx(expected_physical_emissions)
    discount_factor = float(costs.annuity_to_pv(0.05, 5))
    for tech, flow, offset in (
        ('TechOrdinary', 0.3, 0.4),
        ('TechAnnual', 1.0, 0.2),
    ):
        emiss, d_emiss, obps, d_obps = cost_rows[tech]
        assert emiss == pytest.approx(flow * 0.7 * 5)
        assert d_emiss == pytest.approx(flow * 0.7 * discount_factor)
        assert obps == pytest.approx(-flow * offset * 0.7 * 5)
        assert d_obps == pytest.approx(-flow * offset * 0.7 * discount_factor)
    assert objective - baseline_objective == pytest.approx(reported_obps_total)


@pytest.mark.parametrize(
    'setup_sql',
    [
        """
        DELETE FROM cost_emission WHERE region = 'Testregion' AND period = 2000;
        INSERT INTO output_based_standard
        VALUES (
            'Testregion', 2000, 'emission', 'ordinary_in', 'TechOrdinary',
            'ordinary_out', 0.4, NULL, NULL
        );
        """,
        """
        INSERT INTO output_based_standard
        VALUES (
            'Testregion', 2000, 'emission', 'annual_in', 'TechOrdinary',
            'ordinary_out', 0.4, NULL, NULL
        );
        """,
    ],
    ids=['missing-emissions-price', 'missing-active-process'],
)
def test_output_based_standard_rejects_incomplete_rows(tmp_path: Path, setup_sql: str) -> None:
    db_path = _build_feature_database(tmp_path, 'invalid_obps', setup_sql)

    with pytest.raises((ValueError, RuntimeError), match='validate_output_based_standard'):
        _run_feature_model(db_path, tmp_path)


def test_writer_upgrades_old_v4_output_cost_schema_for_obps(tmp_path: Path) -> None:
    db_path = _build_feature_database(
        tmp_path,
        'old_output_schema',
        """
        DROP TABLE output_cost;
        CREATE TABLE output_cost
        (
            scenario TEXT,
            region TEXT,
            sector TEXT,
            period INTEGER,
            tech TEXT,
            vintage INTEGER,
            d_invest REAL,
            d_fixed REAL,
            d_var REAL,
            d_emiss REAL,
            invest REAL,
            fixed REAL,
            var REAL,
            emiss REAL,
            units TEXT,
            PRIMARY KEY (scenario, region, period, tech, vintage)
        );
        INSERT INTO output_based_standard
        VALUES (
            'Testregion', 2000, 'emission', 'ordinary_in', 'TechOrdinary',
            'ordinary_out', 0.4, NULL, NULL
        );
        """,
    )

    _run_feature_model(db_path, tmp_path)

    with contextlib.closing(sqlite3.connect(db_path)) as con:
        columns = {row[1] for row in con.execute('PRAGMA table_info(output_cost)').fetchall()}
        credit = con.execute(
            """
            SELECT obps
            FROM output_cost
            WHERE scenario = 'aces feature test' AND tech = 'TechOrdinary' AND period = 2000
            """
        ).fetchone()[0]

    assert {'obps', 'd_obps'} <= columns
    assert credit == pytest.approx(-0.3 * 0.4 * 0.7 * 5)
