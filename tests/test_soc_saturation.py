"""
Unit tests for src.soc_saturation (Hassink 1997 SOC saturation model).

Run with:  pytest tests/test_soc_saturation.py -v
"""
import math
from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from src.soc_saturation import (
    HASSINK_INTERCEPT_G_KG,
    HASSINK_SLOPE_G_KG,
    SaturationInputs,
    SaturationResult,
    add_saturation_columns,
    c_sat_stock_tC_ha,
    calculate_c_saturation,
    calculate_saturation,
    summarise_saturation,
    validate_saturation_dataframe,
    with_method,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


VALID_INPUTS = SaturationInputs(
    clay_pct=30.0,
    silt_pct=25.0,
    bulk_density_g_cm3=1.25,
    depth_cm=30.0,
    current_soc_stock_tC_ha=40.0,
)


VALID_DF = pd.DataFrame([
    {  # tropical
        "clay_pct": 45.0, "silt_pct": 20.0,
        "bulk_density_g_cm3": 1.15, "depth_cm": 30.0,
        "soc_stock_tC_ha": 55.0,
    },
    {  # temperate
        "clay_pct": 25.0, "silt_pct": 40.0,
        "bulk_density_g_cm3": 1.30, "depth_cm": 30.0,
        "soc_stock_tC_ha": 70.0,
    },
    {  # sandy / low clay
        "clay_pct": 5.0, "silt_pct": 10.0,
        "bulk_density_g_cm3": 1.55, "depth_cm": 30.0,
        "soc_stock_tC_ha": 15.0,
    },
])


# ===========================================================================
# 1. calculate_c_saturation — Hassink 1997 pedotransfer
# ===========================================================================


class TestCalculateCSaturation:
    def test_hassink_equation_matches_paper(self):
        """C_sat = 4.09 + 0.37 * (clay+silt)."""
        result = calculate_c_saturation(30.0, 25.0, method="hassink")
        expected = 4.09 + 0.37 * (30.0 + 25.0)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_six_method_uses_different_coefficients(self):
        hassink = calculate_c_saturation(30.0, 25.0, method="hassink")
        six = calculate_c_saturation(30.0, 25.0, method="six")
        assert hassink != six

    def test_zero_clay_silt_equals_intercept(self):
        result = calculate_c_saturation(0.0, 0.0)
        assert result == pytest.approx(HASSINK_INTERCEPT_G_KG, rel=1e-6)

    def test_monotonic_increase_with_clay(self):
        low = calculate_c_saturation(10.0, 20.0)
        high = calculate_c_saturation(40.0, 20.0)
        assert high > low

    def test_negative_clay_raises(self):
        with pytest.raises(ValueError, match="clay_pct"):
            calculate_c_saturation(-5.0, 20.0)

    def test_clay_over_100_raises(self):
        with pytest.raises(ValueError, match="clay_pct"):
            calculate_c_saturation(105.0, 20.0)

    def test_negative_silt_raises(self):
        with pytest.raises(ValueError, match="silt_pct"):
            calculate_c_saturation(20.0, -1.0)

    def test_clay_plus_silt_over_100_raises(self):
        with pytest.raises(ValueError, match="clay_pct \\+ silt_pct"):
            calculate_c_saturation(60.0, 60.0)

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown method"):
            calculate_c_saturation(30.0, 25.0, method="bogus")

    def test_slope_matches_published_value(self):
        """Slope coefficient must equal 0.37 g C/kg per % fine fraction."""
        assert HASSINK_SLOPE_G_KG == pytest.approx(0.37, rel=1e-12)


# ===========================================================================
# 2. c_sat_stock_tC_ha — conversion to field stock
# ===========================================================================


class TestCSatStock:
    def test_conversion_formula(self):
        """stock = c_sat * BD * depth * 0.1 (tC/ha)."""
        result = c_sat_stock_tC_ha(20.0, 1.2, 30.0)
        expected = 20.0 * 1.2 * 30.0 * 0.1
        assert result == pytest.approx(expected, rel=1e-6)

    def test_zero_concentration_yields_zero(self):
        assert c_sat_stock_tC_ha(0.0, 1.2, 30.0) == 0.0

    def test_doubling_depth_doubles_stock(self):
        a = c_sat_stock_tC_ha(20.0, 1.2, 30.0)
        b = c_sat_stock_tC_ha(20.0, 1.2, 60.0)
        assert b == pytest.approx(2 * a, rel=1e-6)

    def test_negative_concentration_raises(self):
        with pytest.raises(ValueError, match="c_sat_g_per_kg"):
            c_sat_stock_tC_ha(-1.0, 1.2, 30.0)

    def test_bulk_density_too_low_raises(self):
        with pytest.raises(ValueError, match="bulk_density"):
            c_sat_stock_tC_ha(20.0, 0.01, 30.0)

    def test_bulk_density_too_high_raises(self):
        with pytest.raises(ValueError, match="bulk_density"):
            c_sat_stock_tC_ha(20.0, 3.5, 30.0)

    def test_zero_depth_raises(self):
        with pytest.raises(ValueError, match="depth_cm"):
            c_sat_stock_tC_ha(20.0, 1.2, 0.0)

    def test_excessive_depth_raises(self):
        with pytest.raises(ValueError, match="depth_cm"):
            c_sat_stock_tC_ha(20.0, 1.2, 500.0)


# ===========================================================================
# 3. calculate_saturation — high-level wrapper
# ===========================================================================


class TestCalculateSaturation:
    def test_returns_saturation_result(self):
        result = calculate_saturation(VALID_INPUTS)
        assert isinstance(result, SaturationResult)

    def test_deficit_nonnegative_when_undersaturated(self):
        result = calculate_saturation(VALID_INPUTS)
        assert result.saturation_deficit_tC_ha >= 0

    def test_ratio_less_than_one_when_undersaturated(self):
        result = calculate_saturation(VALID_INPUTS)
        assert 0.0 < result.saturation_ratio < 1.0

    def test_supersaturation_clips_deficit_to_zero(self):
        """Measured SOC > saturation stock → deficit must be 0."""
        inputs = SaturationInputs(
            clay_pct=5.0, silt_pct=5.0,           # low fine-fraction soil
            bulk_density_g_cm3=1.4, depth_cm=30.0,
            current_soc_stock_tC_ha=500.0,         # unrealistic high SOC
        )
        result = calculate_saturation(inputs)
        assert result.saturation_deficit_tC_ha == 0.0
        assert result.saturation_ratio >= 1.0

    def test_inputs_are_immutable(self):
        with pytest.raises(FrozenInstanceError):
            VALID_INPUTS.clay_pct = 99.0  # type: ignore[misc]

    def test_result_is_immutable(self):
        result = calculate_saturation(VALID_INPUTS)
        with pytest.raises(FrozenInstanceError):
            result.saturation_deficit_tC_ha = 0.0  # type: ignore[misc]

    def test_method_six_option(self):
        inputs = SaturationInputs(
            clay_pct=30.0, silt_pct=25.0,
            bulk_density_g_cm3=1.25, depth_cm=30.0,
            current_soc_stock_tC_ha=40.0,
            method="six",
        )
        result = calculate_saturation(inputs)
        assert result.method == "six"

    def test_non_dataclass_input_raises(self):
        with pytest.raises(TypeError):
            calculate_saturation({"clay_pct": 30})  # type: ignore[arg-type]

    def test_negative_current_soc_raises(self):
        bad = SaturationInputs(
            clay_pct=30.0, silt_pct=25.0,
            bulk_density_g_cm3=1.25, depth_cm=30.0,
            current_soc_stock_tC_ha=-1.0,
        )
        with pytest.raises(ValueError, match="current_soc_stock_tC_ha"):
            calculate_saturation(bad)

    def test_ratio_echoes_relationship(self):
        """ratio == current / c_sat_stock (within rounding)."""
        result = calculate_saturation(VALID_INPUTS)
        assert result.saturation_ratio == pytest.approx(
            result.current_soc_stock_tC_ha / result.c_sat_stock_tC_ha,
            abs=0.01,
        )


# ===========================================================================
# 4. with_method — immutable updater
# ===========================================================================


class TestWithMethod:
    def test_returns_new_instance(self):
        updated = with_method(VALID_INPUTS, "six")
        assert updated is not VALID_INPUTS
        assert updated.method == "six"

    def test_original_unchanged(self):
        with_method(VALID_INPUTS, "six")
        assert VALID_INPUTS.method == "hassink"

    def test_bad_method_raises(self):
        with pytest.raises(ValueError, match="Unknown method"):
            with_method(VALID_INPUTS, "not_a_method")


# ===========================================================================
# 5. add_saturation_columns — batch DataFrame helper
# ===========================================================================


class TestAddSaturationColumns:
    def test_returns_new_dataframe(self):
        original_cols = list(VALID_DF.columns)
        result = add_saturation_columns(VALID_DF)
        assert list(VALID_DF.columns) == original_cols
        assert "c_sat_g_per_kg" in result.columns
        assert "saturation_deficit_tC_ha" in result.columns

    def test_values_are_finite_for_valid_rows(self):
        result = add_saturation_columns(VALID_DF)
        assert result["c_sat_g_per_kg"].notna().all()
        assert result["saturation_deficit_tC_ha"].notna().all()

    def test_bad_row_yields_nan(self):
        df_bad = pd.DataFrame([{
            "clay_pct": 200.0,        # invalid
            "silt_pct": 20.0,
            "bulk_density_g_cm3": 1.2,
            "depth_cm": 30.0,
            "soc_stock_tC_ha": 40.0,
        }])
        result = add_saturation_columns(df_bad)
        assert math.isnan(result["c_sat_g_per_kg"].iloc[0])

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="Unknown method"):
            add_saturation_columns(VALID_DF, method="bogus")

    def test_nan_rows_yield_nan(self):
        df_with_nan = pd.concat([
            VALID_DF,
            pd.DataFrame([{
                "clay_pct": np.nan, "silt_pct": 20.0,
                "bulk_density_g_cm3": 1.2, "depth_cm": 30.0,
                "soc_stock_tC_ha": 40.0,
            }]),
        ], ignore_index=True)
        result = add_saturation_columns(df_with_nan)
        assert math.isnan(result["c_sat_g_per_kg"].iloc[-1])


# ===========================================================================
# 6. validate_saturation_dataframe
# ===========================================================================


class TestValidateSaturationDataframe:
    def test_valid_passes(self):
        validate_saturation_dataframe(VALID_DF)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_saturation_dataframe(pd.DataFrame())

    def test_missing_column_raises(self):
        bad = VALID_DF.drop(columns=["clay_pct"])
        with pytest.raises(ValueError, match="missing required columns"):
            validate_saturation_dataframe(bad)

    def test_non_dataframe_raises(self):
        with pytest.raises(TypeError):
            validate_saturation_dataframe([1, 2, 3])  # type: ignore[arg-type]

    def test_non_numeric_column_raises(self):
        bad = VALID_DF.copy()
        bad["clay_pct"] = ["a", "b", "c"]
        with pytest.raises(ValueError, match="numeric"):
            validate_saturation_dataframe(bad)


# ===========================================================================
# 7. summarise_saturation
# ===========================================================================


class TestSummariseSaturation:
    def test_summary_keys(self):
        enriched = add_saturation_columns(VALID_DF)
        summary = summarise_saturation(enriched)
        for k in (
            "mean_deficit_tC_ha",
            "total_deficit_tC_ha",
            "mean_ratio",
            "n_saturated",
            "n_valid",
        ):
            assert k in summary

    def test_summary_counts_saturated_rows(self):
        df = pd.DataFrame([{
            "clay_pct": 5.0, "silt_pct": 5.0,
            "bulk_density_g_cm3": 1.4, "depth_cm": 30.0,
            "soc_stock_tC_ha": 500.0,        # super-saturated
        }])
        enriched = add_saturation_columns(df)
        summary = summarise_saturation(enriched)
        assert summary["n_saturated"] == 1

    def test_summary_handles_all_nan(self):
        df = pd.DataFrame([{
            "saturation_deficit_tC_ha": np.nan,
            "saturation_ratio": np.nan,
        }])
        summary = summarise_saturation(df)
        assert summary["n_valid"] == 0
        assert summary["mean_deficit_tC_ha"] is None

    def test_summary_missing_columns_raises(self):
        with pytest.raises(ValueError, match="missing column"):
            summarise_saturation(pd.DataFrame({"foo": [1]}))


# ===========================================================================
# 8. End-to-end smoke — sample_data/*.csv scenarios
# ===========================================================================


class TestSampleDataScenarios:
    def test_sample_csv_loads_and_computes(self):
        from pathlib import Path

        path = (
            Path(__file__).parent.parent
            / "sample_data"
            / "soc_saturation_scenarios.csv"
        )
        df = pd.read_csv(path)
        enriched = add_saturation_columns(df)
        # Every row must produce finite saturation metrics
        assert enriched["c_sat_g_per_kg"].notna().all()
        assert (enriched["c_sat_g_per_kg"] > 0).all()
