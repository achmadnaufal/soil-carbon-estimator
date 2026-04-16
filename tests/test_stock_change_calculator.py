"""
Tests for src/stock_change_calculator.py.

Run with:  pytest tests/test_stock_change_calculator.py -v

Coverage target: >= 80 %
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.stock_change_calculator import (
    StockChangeSummary,
    compute_stock_change,
    summarise_stock_change,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_survey(site_ids, soc_values, errors=None):
    """Return a minimal survey DataFrame."""
    data = {"site_id": site_ids, "soc_stock_tC_ha": soc_values}
    if errors is not None:
        data["error_tC_ha"] = errors
    return pd.DataFrame(data)


@pytest.fixture()
def paired_surveys():
    t0 = _make_survey(["A", "B", "C"], [80.0, 60.0, 100.0])
    t1 = _make_survey(["A", "B", "C"], [88.0, 66.0, 110.0])
    return t0, t1


# ---------------------------------------------------------------------------
# TestComputeStockChange — happy path
# ---------------------------------------------------------------------------


class TestComputeStockChange:
    def test_returns_new_dataframe(self, paired_surveys):
        t0, t1 = paired_surveys
        result = compute_stock_change(t0, t1, years_elapsed=4.0)
        assert isinstance(result, pd.DataFrame)
        assert result is not t0
        assert result is not t1

    def test_does_not_mutate_inputs(self, paired_surveys):
        t0, t1 = paired_surveys
        t0_cols_before = list(t0.columns)
        t1_cols_before = list(t1.columns)
        compute_stock_change(t0, t1, years_elapsed=4.0)
        assert list(t0.columns) == t0_cols_before
        assert list(t1.columns) == t1_cols_before

    def test_delta_values_correct(self, paired_surveys):
        t0, t1 = paired_surveys
        result = compute_stock_change(t0, t1, years_elapsed=4.0)
        expected = [8.0, 6.0, 10.0]
        assert list(result["delta_soc_tC_ha"]) == pytest.approx(expected)

    def test_annual_rate_correct(self, paired_surveys):
        t0, t1 = paired_surveys
        result = compute_stock_change(t0, t1, years_elapsed=4.0)
        expected = [2.0, 1.5, 2.5]
        assert list(result["annual_rate_tC_ha_yr"]) == pytest.approx(expected)

    def test_ci_bounds_symmetric_around_delta(self, paired_surveys):
        t0, t1 = paired_surveys
        result = compute_stock_change(t0, t1, years_elapsed=4.0)
        for _, row in result.iterrows():
            half = (row["ci_upper_tC_ha"] - row["ci_lower_tC_ha"]) / 2
            centre = (row["ci_upper_tC_ha"] + row["ci_lower_tC_ha"]) / 2
            assert abs(centre - row["delta_soc_tC_ha"]) < 1e-6
            assert half > 0

    def test_output_columns_present(self, paired_surveys):
        t0, t1 = paired_surveys
        result = compute_stock_change(t0, t1, years_elapsed=4.0)
        expected_cols = {
            "site_id",
            "soc_t0_tC_ha",
            "soc_t1_tC_ha",
            "delta_soc_tC_ha",
            "annual_rate_tC_ha_yr",
            "ci_lower_tC_ha",
            "ci_upper_tC_ha",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_inner_join_drops_unmatched_sites(self):
        t0 = _make_survey(["A", "B", "X"], [80.0, 60.0, 50.0])
        t1 = _make_survey(["A", "B", "Y"], [88.0, 66.0, 55.0])
        result = compute_stock_change(t0, t1, years_elapsed=2.0)
        assert set(result["site_id"]) == {"A", "B"}

    def test_determinism(self, paired_surveys):
        t0, t1 = paired_surveys
        r1 = compute_stock_change(t0, t1, years_elapsed=4.0)
        r2 = compute_stock_change(t0, t1, years_elapsed=4.0)
        pd.testing.assert_frame_equal(r1, r2)

    def test_custom_error_col_widens_ci(self, paired_surveys):
        t0, t1 = paired_surveys
        t0_err = t0.copy()
        t1_err = t1.copy()
        # Give a large explicit error
        t0_err["error_tC_ha"] = 20.0
        t1_err["error_tC_ha"] = 20.0
        result_default = compute_stock_change(t0, t1, years_elapsed=4.0)
        result_custom = compute_stock_change(
            t0_err, t1_err, years_elapsed=4.0, error_col="error_tC_ha"
        )
        # CI width should be larger when error is larger
        def width(df):
            return (df["ci_upper_tC_ha"] - df["ci_lower_tC_ha"]).mean()

        assert width(result_custom) > width(result_default)

    def test_single_site(self):
        t0 = _make_survey(["S1"], [50.0])
        t1 = _make_survey(["S1"], [55.0])
        result = compute_stock_change(t0, t1, years_elapsed=1.0)
        assert len(result) == 1
        assert result["delta_soc_tC_ha"].iloc[0] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# TestComputeStockChangeErrors — invalid inputs
# ---------------------------------------------------------------------------


class TestComputeStockChangeErrors:
    def test_raises_type_error_for_non_dataframe_t0(self):
        t1 = _make_survey(["A"], [80.0])
        with pytest.raises(TypeError, match="survey_t0"):
            compute_stock_change("not a df", t1, years_elapsed=1.0)

    def test_raises_type_error_for_non_dataframe_t1(self):
        t0 = _make_survey(["A"], [80.0])
        with pytest.raises(TypeError, match="survey_t1"):
            compute_stock_change(t0, 42, years_elapsed=1.0)

    def test_raises_value_error_for_zero_years(self, paired_surveys):
        t0, t1 = paired_surveys
        with pytest.raises(ValueError, match="years_elapsed"):
            compute_stock_change(t0, t1, years_elapsed=0.0)

    def test_raises_value_error_for_negative_years(self, paired_surveys):
        t0, t1 = paired_surveys
        with pytest.raises(ValueError, match="years_elapsed"):
            compute_stock_change(t0, t1, years_elapsed=-2.0)

    def test_raises_value_error_missing_soc_column(self):
        t0 = pd.DataFrame({"site_id": ["A"], "other_col": [1.0]})
        t1 = _make_survey(["A"], [80.0])
        with pytest.raises(ValueError, match="soc_stock_tC_ha"):
            compute_stock_change(t0, t1, years_elapsed=1.0)

    def test_raises_value_error_no_matching_sites(self):
        t0 = _make_survey(["A"], [80.0])
        t1 = _make_survey(["Z"], [80.0])
        with pytest.raises(ValueError, match="No matching sites"):
            compute_stock_change(t0, t1, years_elapsed=1.0)


# ---------------------------------------------------------------------------
# Parametrized: annualised rate across different time spans
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "years, expected_rate",
    [
        (1.0, 8.0),
        (2.0, 4.0),
        (4.0, 2.0),
        (10.0, 0.8),
    ],
)
def test_annual_rate_parametrized(years, expected_rate):
    t0 = _make_survey(["X"], [80.0])
    t1 = _make_survey(["X"], [88.0])
    result = compute_stock_change(t0, t1, years_elapsed=years)
    assert result["annual_rate_tC_ha_yr"].iloc[0] == pytest.approx(expected_rate)


# ---------------------------------------------------------------------------
# TestSummariseStockChange
# ---------------------------------------------------------------------------


class TestSummariseStockChange:
    def test_returns_frozen_dataclass(self, paired_surveys):
        t0, t1 = paired_surveys
        df = compute_stock_change(t0, t1, years_elapsed=4.0)
        summary = summarise_stock_change(df, years_elapsed=4.0)
        assert isinstance(summary, StockChangeSummary)

    def test_n_sites_correct(self, paired_surveys):
        t0, t1 = paired_surveys
        df = compute_stock_change(t0, t1, years_elapsed=4.0)
        summary = summarise_stock_change(df, years_elapsed=4.0)
        assert summary.n_sites == 3

    def test_mean_delta_correct(self, paired_surveys):
        t0, t1 = paired_surveys
        df = compute_stock_change(t0, t1, years_elapsed=4.0)
        summary = summarise_stock_change(df, years_elapsed=4.0)
        assert summary.mean_delta_tC_ha == pytest.approx(8.0)

    def test_total_delta_correct(self, paired_surveys):
        t0, t1 = paired_surveys
        df = compute_stock_change(t0, t1, years_elapsed=4.0)
        summary = summarise_stock_change(df, years_elapsed=4.0)
        assert summary.total_delta_tC_ha == pytest.approx(24.0)

    def test_ci_bounds_ordered(self, paired_surveys):
        t0, t1 = paired_surveys
        df = compute_stock_change(t0, t1, years_elapsed=4.0)
        summary = summarise_stock_change(df, years_elapsed=4.0)
        assert summary.ci_lower_tC_ha <= summary.mean_delta_tC_ha
        assert summary.ci_upper_tC_ha >= summary.mean_delta_tC_ha

    def test_years_elapsed_recorded(self, paired_surveys):
        t0, t1 = paired_surveys
        df = compute_stock_change(t0, t1, years_elapsed=4.0)
        summary = summarise_stock_change(df, years_elapsed=4.0)
        assert summary.years_elapsed == 4.0

    def test_single_site_zero_ci_half_width(self):
        t0 = _make_survey(["S1"], [50.0])
        t1 = _make_survey(["S1"], [60.0])
        df = compute_stock_change(t0, t1, years_elapsed=5.0)
        summary = summarise_stock_change(df, years_elapsed=5.0)
        # With n=1 there is no standard error; CI collapses to the point estimate
        assert summary.ci_lower_tC_ha == pytest.approx(summary.ci_upper_tC_ha)

    def test_raises_on_empty_change_df(self):
        empty = pd.DataFrame(
            columns=["site_id", "delta_soc_tC_ha", "annual_rate_tC_ha_yr"]
        )
        with pytest.raises(ValueError, match="empty"):
            summarise_stock_change(empty, years_elapsed=1.0)
