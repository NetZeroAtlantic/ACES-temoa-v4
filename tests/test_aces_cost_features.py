"""Regression tests for ACES cost features ported to the v4 model."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from temoa._internal.temoa_sequencer import TemoaSequencer
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
