"""
Tests for src/depth_profile.py.

Run with:  pytest tests/test_depth_profile.py -v
Coverage target: >= 80 %.

Test classes
------------
TestInterpolateSOCProfile          -- happy path, ordering, clamping
TestInterpolateSOCProfileEdgeCases -- empty / NaN / invalid inputs
TestIntegrateSOCToDepth            -- integration within and beyond samples
TestIntegrateSOCEdgeCases          -- single-horizon, extrapolate=False, errors
TestHarmoniseToReferenceDepth      -- multi-site grouping, immutability
TestImmutability                   -- inputs are never mutated
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.depth_profile import (
    harmonise_to_reference_depth,
    integrate_soc_to_depth,
    interpolate_soc_profile,
)


# ---------------------------------------------------------------------------
# Realistic fixtures (Indonesian tropical-soil profile shape)
# ---------------------------------------------------------------------------

# Three-horizon profile from a tropical-forest plot in West Java:
#   0-10 cm: high SOC density
#   10-20 cm: moderate
#   20-40 cm: lower (below root zone)
TROPICAL_DEPTHS = [10.0, 20.0, 40.0]
TROPICAL_STOCKS = [25.0, 22.0, 18.0]   # tC/ha per horizon

# Five-horizon cropland profile (more granular)
CROPLAND_DEPTHS = [5.0, 15.0, 30.0, 60.0, 100.0]
CROPLAND_STOCKS = [12.0, 18.0, 22.0, 25.0, 15.0]


# ===========================================================================
# 1. interpolate_soc_profile -- happy path
# ===========================================================================


class TestInterpolateSOCProfile:
    """Tests for depth_profile.interpolate_soc_profile."""

    def test_basic_interpolation(self):
        """Linear interpolation between two horizons returns midpoint value."""
        result = interpolate_soc_profile([10, 20, 40], [25.0, 22.0, 18.0], [15, 30])
        # at depth 15 -> halfway between 25 and 22 -> 23.5
        # at depth 30 -> halfway between 22 and 18 -> 20.0
        assert result == [23.5, 20.0]

    def test_returns_list_of_floats(self):
        """Output is a list of plain Python floats."""
        result = interpolate_soc_profile([10, 30], [20.0, 10.0], [20])
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_target_at_measured_depth_returns_measured_value(self):
        """A target depth that matches a sampled horizon returns its stock."""
        result = interpolate_soc_profile([10, 20, 40], [25.0, 22.0, 18.0], [10, 20, 40])
        assert result == [25.0, 22.0, 18.0]

    def test_unsorted_input_is_handled(self):
        """Input depths in descending order produce the same result."""
        ascending = interpolate_soc_profile([10, 20, 40], [25.0, 22.0, 18.0], [15])
        descending = interpolate_soc_profile([40, 20, 10], [18.0, 22.0, 25.0], [15])
        assert ascending == descending

    def test_target_above_shallowest_clamps(self):
        """Target shallower than the shallowest sample clamps to it."""
        result = interpolate_soc_profile([10, 20], [25.0, 22.0], [5])
        assert result == [25.0]

    def test_target_below_deepest_clamps(self):
        """Target deeper than the deepest sample clamps to it (no extrapolation)."""
        result = interpolate_soc_profile([10, 20], [25.0, 22.0], [50])
        assert result == [22.0]

    def test_preserves_target_order(self):
        """Output preserves the order of the *target_depths_cm* input."""
        out = interpolate_soc_profile([10, 30], [20.0, 10.0], [25, 15, 30])
        # at 25 -> 12.5; at 15 -> 17.5; at 30 -> 10.0
        assert out == [12.5, 17.5, 10.0]


# ===========================================================================
# 2. interpolate_soc_profile -- edge / invalid inputs
# ===========================================================================


class TestInterpolateSOCProfileEdgeCases:
    """Edge cases and invalid-input handling."""

    def test_empty_profile_raises(self):
        with pytest.raises(ValueError, match="Profile is empty"):
            interpolate_soc_profile([], [], [10])

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="Length mismatch"):
            interpolate_soc_profile([10, 20], [25.0], [15])

    def test_nan_in_depths_raises(self):
        with pytest.raises(ValueError, match="NaN"):
            interpolate_soc_profile([10, float("nan")], [25.0, 22.0], [15])

    def test_negative_depth_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            interpolate_soc_profile([-10, 20], [25.0, 22.0], [15])

    def test_negative_stock_raises(self):
        with pytest.raises(ValueError, match="SOC stocks must be >= 0"):
            interpolate_soc_profile([10, 20], [25.0, -5.0], [15])

    def test_depth_above_max_raises(self):
        with pytest.raises(ValueError, match="physical maximum"):
            interpolate_soc_profile([10, 500], [25.0, 22.0], [15])

    def test_duplicate_depths_raises(self):
        with pytest.raises(ValueError, match="Duplicate depth"):
            interpolate_soc_profile([10, 20, 20], [25.0, 22.0, 18.0], [15])

    def test_string_input_raises_type_error(self):
        with pytest.raises(TypeError):
            interpolate_soc_profile("10,20", "25,22", [15])

    def test_empty_target_depths_raises(self):
        with pytest.raises(ValueError, match="'target_depths_cm' is empty"):
            interpolate_soc_profile([10, 20], [25.0, 22.0], [])


# ===========================================================================
# 3. integrate_soc_to_depth -- happy path
# ===========================================================================


class TestIntegrateSOCToDepth:
    """Tests for depth_profile.integrate_soc_to_depth."""

    def test_target_at_deepest_returns_total(self):
        """Integrating to the deepest measured depth returns the total stock."""
        result = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 40)
        assert result == pytest.approx(sum(TROPICAL_STOCKS), rel=1e-6)

    def test_target_between_horizons(self):
        """Integrating to a depth between horizons interpolates the partial layer."""
        # Horizons: cum at 10=25, at 20=47, at 40=65.
        # Target=30 -> 47 + (30-20)/(40-20) * (65-47) = 47 + 9 = 56
        result = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 30)
        assert result == pytest.approx(56.0, rel=1e-6)

    def test_target_at_shallowest_partial(self):
        """Target shallower than first horizon returns proportional fraction."""
        # First horizon ends at 10 cm with 25 tC/ha.
        # Target=5 -> 5/10 * 25 = 12.5
        result = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 5)
        assert result == pytest.approx(12.5, rel=1e-6)

    def test_extrapolation_increases_with_depth(self):
        """Extrapolated cumulative stock is monotonically non-decreasing."""
        s_50 = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 50)
        s_100 = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 100)
        s_200 = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 200)
        assert s_50 < s_100 < s_200

    def test_extrapolation_above_total_measured(self):
        """Extrapolated cumulative stock exceeds the measured total."""
        measured = sum(TROPICAL_STOCKS)
        extrapolated = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 100)
        assert extrapolated > measured

    def test_extrapolate_false_raises(self):
        """When extrapolate=False, target beyond deepest raises ValueError."""
        with pytest.raises(ValueError, match="extrapolate=False"):
            integrate_soc_to_depth(
                TROPICAL_DEPTHS, TROPICAL_STOCKS, 100, extrapolate=False
            )

    def test_cropland_profile_round_trip(self):
        """Integrating to deepest depth equals sum of horizon stocks."""
        result = integrate_soc_to_depth(CROPLAND_DEPTHS, CROPLAND_STOCKS, 100)
        assert result == pytest.approx(sum(CROPLAND_STOCKS), rel=1e-6)

    def test_result_is_rounded(self):
        """Returned value is rounded to four decimal places."""
        result = integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 23)
        assert result == round(result, 4)


# ===========================================================================
# 4. integrate_soc_to_depth -- edge cases / invalid inputs
# ===========================================================================


class TestIntegrateSOCEdgeCases:
    def test_single_horizon_within_returns_proportion(self):
        """Single-horizon profile - target inside scales linearly."""
        # 30 tC/ha contained in 0-30 cm; target=15 -> 15.0
        result = integrate_soc_to_depth([30.0], [30.0], 15)
        assert result == pytest.approx(15.0, rel=1e-6)

    def test_single_horizon_extrapolates_with_default_decay(self):
        """Single-horizon extrapolation uses default decay constant."""
        # Should produce a positive but bounded extra stock
        result = integrate_soc_to_depth([30.0], [30.0], 60)
        assert result > 30.0
        assert result < 60.0  # exponential decay caps the contribution

    def test_zero_target_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 0)

    def test_negative_target_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, -5)

    def test_target_above_max_raises(self):
        with pytest.raises(ValueError, match="exceeds physical maximum"):
            integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, 9999)

    def test_non_numeric_target_raises(self):
        with pytest.raises(TypeError):
            integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, "deep")

    def test_nan_target_raises(self):
        with pytest.raises(ValueError, match="finite"):
            integrate_soc_to_depth(TROPICAL_DEPTHS, TROPICAL_STOCKS, float("nan"))

    def test_zero_stock_profile_returns_zero(self):
        """All-zero stocks integrate to zero (no SOC to harmonise)."""
        result = integrate_soc_to_depth([10, 20, 30], [0.0, 0.0, 0.0], 30)
        assert result == 0.0


# ===========================================================================
# 5. harmonise_to_reference_depth -- multi-site behaviour
# ===========================================================================


class TestHarmoniseToReferenceDepth:
    @pytest.fixture()
    def long_df(self):
        return pd.DataFrame(
            {
                "site_id": ["TH001", "TH001", "TH002", "TH002", "TH002"],
                "depth_cm": [10.0, 30.0, 10.0, 20.0, 40.0],
                "soc_stock_tC_ha": [25.0, 22.0, 28.0, 24.0, 18.0],
            }
        )

    def test_returns_one_row_per_site(self, long_df):
        result = harmonise_to_reference_depth(long_df, target_depth_cm=30)
        assert len(result) == 2
        assert set(result["site_id"]) == {"TH001", "TH002"}

    def test_columns_are_correct(self, long_df):
        result = harmonise_to_reference_depth(long_df, target_depth_cm=30)
        assert sorted(result.columns.tolist()) == [
            "n_horizons",
            "reference_depth_cm",
            "site_id",
            "soc_stock_tC_ha",
        ]

    def test_reference_depth_recorded(self, long_df):
        result = harmonise_to_reference_depth(long_df, target_depth_cm=30)
        assert (result["reference_depth_cm"] == 30.0).all()

    def test_n_horizons_per_site(self, long_df):
        result = harmonise_to_reference_depth(long_df, target_depth_cm=30)
        result = result.set_index("site_id")
        assert int(result.loc["TH001", "n_horizons"]) == 2
        assert int(result.loc["TH002", "n_horizons"]) == 3

    def test_missing_column_raises(self):
        bad_df = pd.DataFrame({"site_id": ["A"], "depth_cm": [10]})
        with pytest.raises(ValueError, match="missing required columns"):
            harmonise_to_reference_depth(bad_df, target_depth_cm=30)

    def test_empty_dataframe_raises(self):
        empty = pd.DataFrame(columns=["site_id", "depth_cm", "soc_stock_tC_ha"])
        with pytest.raises(ValueError, match="empty"):
            harmonise_to_reference_depth(empty, target_depth_cm=30)

    def test_non_dataframe_raises(self):
        with pytest.raises(TypeError, match="pandas DataFrame"):
            harmonise_to_reference_depth([1, 2, 3], target_depth_cm=30)

    def test_custom_column_names(self):
        df = pd.DataFrame(
            {
                "plot": ["A", "A"],
                "horizon_depth": [10, 30],
                "stock_tCha": [20.0, 18.0],
            }
        )
        result = harmonise_to_reference_depth(
            df,
            target_depth_cm=30,
            site_id_col="plot",
            depth_col="horizon_depth",
            stock_col="stock_tCha",
        )
        assert len(result) == 1
        # full profile to 30 cm -> 38.0
        assert result["soc_stock_tC_ha"].iloc[0] == pytest.approx(38.0, rel=1e-6)


# ===========================================================================
# 6. Immutability invariants
# ===========================================================================


class TestImmutability:
    def test_interpolate_does_not_mutate_inputs(self):
        depths = [10.0, 20.0, 40.0]
        stocks = [25.0, 22.0, 18.0]
        targets = [15.0, 30.0]
        depths_snapshot = list(depths)
        stocks_snapshot = list(stocks)
        targets_snapshot = list(targets)
        interpolate_soc_profile(depths, stocks, targets)
        assert depths == depths_snapshot
        assert stocks == stocks_snapshot
        assert targets == targets_snapshot

    def test_integrate_does_not_mutate_inputs(self):
        depths = [10.0, 20.0, 40.0]
        stocks = [25.0, 22.0, 18.0]
        depths_snapshot = list(depths)
        stocks_snapshot = list(stocks)
        integrate_soc_to_depth(depths, stocks, 30)
        assert depths == depths_snapshot
        assert stocks == stocks_snapshot

    def test_harmonise_does_not_mutate_input_df(self):
        df = pd.DataFrame(
            {
                "site_id": ["A", "A"],
                "depth_cm": [10, 30],
                "soc_stock_tC_ha": [20.0, 18.0],
            }
        )
        snapshot = df.copy(deep=True)
        result = harmonise_to_reference_depth(df, 30)
        pd.testing.assert_frame_equal(df, snapshot)
        assert result is not df
