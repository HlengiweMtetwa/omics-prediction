"""Tests for the WBE mass-balance back-calculation.

The dimensional chain is checked against hand-computed values, because a
back-calculation that is wrong by a factor of 1000 still produces a plausible
looking prevalence.
"""

import numpy as np
import pytest

from omics_wbe.normalize.back_calculation import (
    ExcretionParameters, ParameterUnavailable, back_calculate, back_calculate_mc,
    daily_mass_load_mg, parameters_from_catalog, population_normalised_load,
)


def test_daily_mass_load_dimensional_analysis():
    # 1000 ng/L x 10,000,000 L/day = 10^10 ng/day = 10,000 mg/day
    assert daily_mass_load_mg(1000.0, 10e6) == pytest.approx(10_000.0)


def test_population_normalisation():
    assert population_normalised_load(10_000.0, 100_000) == pytest.approx(100.0)
    assert population_normalised_load(10_000.0, 100_000, per=1) == pytest.approx(0.1)


def test_population_must_be_positive():
    with pytest.raises(ValueError):
        population_normalised_load(1.0, 0)


def test_correction_factor_inverts_pharmacokinetics():
    params = ExcretionParameters(excretion_fraction=0.5, bioavailability=0.5)
    assert params.correction_factor == pytest.approx(4.0)
    params = ExcretionParameters(excretion_fraction=0.25, bioavailability=1.0, molar_correction=2.0)
    assert params.correction_factor == pytest.approx(8.0)


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        ExcretionParameters(excretion_fraction=0.0)
    with pytest.raises(ValueError):
        ExcretionParameters(excretion_fraction=1.5)
    with pytest.raises(ValueError):
        ExcretionParameters(excretion_fraction=0.5, bioavailability=0.0)
    with pytest.raises(ValueError):
        ExcretionParameters(excretion_fraction=0.5, defined_daily_dose_mg=-1)


def test_back_calculate_round_trip():
    params = ExcretionParameters(excretion_fraction=1.0, bioavailability=1.0,
                                 defined_daily_dose_mg=1000.0)
    out = back_calculate(1000.0, 10e6, 100_000, params)
    assert out["mass_load_mg_per_day"] == pytest.approx(10_000.0)
    assert out["analyte_load_mg_per_day_per_1000"] == pytest.approx(100.0)
    assert out["consumption_mg_per_day_per_1000"] == pytest.approx(100.0)
    # 100 mg/day per 1000 people, at a 1000 mg daily dose, is 0.1 people per 1000.
    assert out["treated_prevalence_per_1000"] == pytest.approx(0.1)


def test_doubling_concentration_doubles_the_estimate():
    params = ExcretionParameters(excretion_fraction=0.9, bioavailability=0.55,
                                 defined_daily_dose_mg=2000.0)
    a = back_calculate(1000.0, 10e6, 100_000, params)["treated_prevalence_per_1000"]
    b = back_calculate(2000.0, 10e6, 100_000, params)["treated_prevalence_per_1000"]
    assert b == pytest.approx(2 * a)


def test_monte_carlo_is_deterministic_under_a_seed():
    params = ExcretionParameters(excretion_fraction=0.9, bioavailability=0.55,
                                 defined_daily_dose_mg=2000.0)
    a = back_calculate_mc(1000.0, 10e6, 100_000, params, n_draws=500, seed=7)
    b = back_calculate_mc(1000.0, 10e6, 100_000, params, n_draws=500, seed=7)
    assert a == b


def test_monte_carlo_interval_brackets_the_point_estimate():
    params = ExcretionParameters(excretion_fraction=0.9, bioavailability=0.55,
                                 defined_daily_dose_mg=2000.0)
    point = back_calculate(1000.0, 10e6, 100_000, params)["consumption_mg_per_day_per_1000"]
    mc = back_calculate_mc(1000.0, 10e6, 100_000, params, n_draws=4000, seed=11)
    band = mc["consumption_mg_per_day_per_1000"]
    assert band["ci95_low"] < point < band["ci95_high"]


def test_monte_carlo_bounds_excretion_and_bioavailability_to_physical_range():
    params = ExcretionParameters(excretion_fraction=0.95, bioavailability=0.95)
    mc = back_calculate_mc(1000.0, 10e6, 100_000, params, excretion_cv=0.9,
                           bioavailability_cv=0.9, n_draws=3000, seed=3)
    # Both factors are capped at 1.0, so the correction factor cannot fall below 1.
    assert mc["correction_factor"]["ci95_low"] >= 1.0


def test_catalog_refuses_markers_without_transferable_parameters():
    for biomarker in ("cortisol_cortisone", "isoprostane_8_iso_pgf2a", "capecitabine_5fu"):
        with pytest.raises(ParameterUnavailable):
            parameters_from_catalog(biomarker, defined_daily_dose_mg=100.0)


def test_allow_uncalibrated_still_refuses_when_no_value_exists():
    with pytest.raises(ParameterUnavailable, match="nothing to build parameters from"):
        parameters_from_catalog("cortisol_cortisone", defined_daily_dose_mg=100.0,
                                allow_uncalibrated=True)


def test_metformin_parameters_come_from_the_catalogue():
    params = parameters_from_catalog("metformin", defined_daily_dose_mg=2000.0)
    assert params.excretion_fraction == pytest.approx(0.90)
    assert params.bioavailability == pytest.approx(0.55)
    assert params.correction_factor == pytest.approx(1 / (0.9 * 0.55))
