"""
Unit and integration tests for the soil-carbon-estimator package.

Run with:  pytest tests/ -v
Coverage:  pytest tests/ -v --cov=src --cov-report=term-missing

Coverage target: >= 80 %

Test classes
------------
TestCalculateSOCStock           -- basic correctness of the scalar formula
TestCalculateSOCStockEdgeCases  -- invalid / boundary inputs raise ValueError
TestValidateDataFrame           -- validate_dataframe() guards
TestLoadData                    -- SoilCarbonEstimator.load_data() I/O
TestAddSOCStockColumn           -- immutability and NaN handling
TestAnalyze                     -- SoilCarbonEstimator.analyze() pipeline
TestRunPipeline                 -- integration test via SoilCarbonEstimator.run()
TestFilterValidRows             -- filter_valid_rows() row exclusion logic
TestPreprocess                  -- SoilCarbonEstimator.preprocess() transforms
TestToDataFrame                 -- SoilCarbonEstimator.to_dataframe() flattening
TestDataGenerator               -- generate_sample() data shape and content
TestSOCCalculatorConstants      -- module-level constants are within expected ranges
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Shared fixtures (immutable -- never mutated by tests)
# ---------------------------------------------------------------------------

SAMPLE_CSV = Path(__file__).parent.parent / "demo" / "sample_data.csv"

VALID_DF = pd.DataFrame([
    {"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 2.5, "depth_cm": 30.0},
    {"bulk_density_g_cm3": 1.1, "organic_carbon_pct": 3.0, "depth_cm": 20.0},
    {"bulk_density_g_cm3": 1.35, "organic_carbon_pct": 1.5, "depth_cm": 30.0},
])


# ===========================================================================
# 1. SOC stock calculation -- basic correctness
# ===========================================================================

class TestCalculateSOCStock:
    """Tests for soc_calculator.calculate_soc_stock."""

    def test_basic_calculation(self):
        """Standard mid-range inputs should return the expected value."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.2, 2.5, 30)
        # formula: BD(g/cm3) x (OC% / 100) x depth(cm) x 100 -> tC/ha
        # 1.2 x 0.025 x 30 x 100 = 90.0
        assert result == pytest.approx(90.0, rel=1e-4)

    def test_result_rounded_to_two_decimal_places(self):
        """Return value must be rounded to two decimal places."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.123456, 2.111111, 25)
        assert result == round(result, 2)

    def test_zero_organic_carbon_returns_zero(self):
        """Zero OC% should yield zero stock regardless of other inputs."""
        from src.soc_calculator import calculate_soc_stock
        assert calculate_soc_stock(1.2, 0.0, 30) == 0.0

    def test_minimum_valid_bulk_density(self):
        """Bulk density of exactly 0 should return zero stock."""
        from src.soc_calculator import calculate_soc_stock
        assert calculate_soc_stock(0.0, 2.5, 30) == 0.0

    def test_proportional_to_depth(self):
        """Doubling depth should exactly double the SOC stock."""
        from src.soc_calculator import calculate_soc_stock
        stock_30 = calculate_soc_stock(1.2, 2.5, 30)
        stock_60 = calculate_soc_stock(1.2, 2.5, 60)
        assert stock_60 == pytest.approx(stock_30 * 2, rel=1e-6)

    def test_proportional_to_bulk_density(self):
        """Doubling bulk density should exactly double the SOC stock."""
        from src.soc_calculator import calculate_soc_stock
        stock_low = calculate_soc_stock(0.8, 2.5, 30)
        stock_high = calculate_soc_stock(1.6, 2.5, 30)
        assert stock_high == pytest.approx(stock_low * 2, rel=1e-6)

    def test_proportional_to_oc_percent(self):
        """Doubling OC% should exactly double the SOC stock."""
        from src.soc_calculator import calculate_soc_stock
        stock_low = calculate_soc_stock(1.2, 1.5, 30)
        stock_high = calculate_soc_stock(1.2, 3.0, 30)
        assert stock_high == pytest.approx(stock_low * 2, rel=1e-6)

    def test_realistic_tropical_site(self):
        """Values from demo/sample_data.csv row TH001 should match expected stock."""
        from src.soc_calculator import calculate_soc_stock
        # TH001: BD=1.12, OC=2.85, depth=30
        result = calculate_soc_stock(1.12, 2.85, 30)
        expected = round(1.12 * (2.85 / 100) * 30 * 100, 2)
        assert result == pytest.approx(expected, rel=1e-4)

    def test_peatland_high_oc(self):
        """Peatland sites with high OC% should produce a large but valid stock."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.05, 4.12, 20)
        assert result == pytest.approx(86.52, rel=1e-3)

    def test_returns_float(self):
        """The return type must always be float."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.2, 2.5, 30)
        assert isinstance(result, float)

    def test_maximum_physical_inputs(self):
        """Maximum physical values should succeed without raising."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(2.65, 100.0, 300)
        assert result > 0

    def test_very_shallow_depth(self):
        """A very thin layer (1 cm) should produce a small but valid result."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.2, 2.5, 1)
        assert result == pytest.approx(3.0, rel=1e-4)


# ===========================================================================
# 2. SOC stock calculation -- edge cases / invalid inputs
# ===========================================================================

class TestCalculateSOCStockEdgeCases:
    """Tests for validation inside calculate_soc_stock."""

    def test_negative_bulk_density_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="bulk_density"):
            calculate_soc_stock(-0.1, 2.5, 30)

    def test_bulk_density_exceeds_max_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="bulk_density"):
            calculate_soc_stock(3.0, 2.5, 30)  # > 2.65 g/cm3

    def test_negative_organic_carbon_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="organic_carbon_pct"):
            calculate_soc_stock(1.2, -1.0, 30)

    def test_organic_carbon_over_100_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="organic_carbon_pct"):
            calculate_soc_stock(1.2, 101.0, 30)

    def test_zero_depth_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="depth_cm"):
            calculate_soc_stock(1.2, 2.5, 0)

    def test_negative_depth_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="depth_cm"):
            calculate_soc_stock(1.2, 2.5, -10)

    def test_depth_exceeds_max_raises(self):
        from src.soc_calculator import calculate_soc_stock
        with pytest.raises(ValueError, match="depth_cm"):
            calculate_soc_stock(1.2, 2.5, 500)  # > 300 cm limit

    def test_bulk_density_at_exact_max_does_not_raise(self):
        """Bulk density exactly at the physical maximum should be accepted."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(2.65, 2.5, 30)
        assert result > 0

    def test_oc_at_exactly_100_does_not_raise(self):
        """OC% at exactly 100 is valid (edge of range)."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(0.5, 100.0, 10)
        assert result > 0


# ===========================================================================
# 3. Input validation -- validate_dataframe
# ===========================================================================

class TestValidateDataFrame:
    """Tests for soc_calculator.validate_dataframe."""

    def test_valid_dataframe_passes(self):
        from src.soc_calculator import validate_dataframe
        validate_dataframe(VALID_DF)  # should not raise

    def test_empty_dataframe_raises(self):
        from src.soc_calculator import validate_dataframe
        with pytest.raises(ValueError, match="empty"):
            validate_dataframe(pd.DataFrame())

    def test_missing_required_column_raises(self):
        from src.soc_calculator import validate_dataframe
        incomplete = VALID_DF.drop(columns=["bulk_density_g_cm3"])
        with pytest.raises(ValueError, match="missing required columns"):
            validate_dataframe(incomplete)

    def test_all_three_required_columns_missing_raises(self):
        """A completely unrelated DataFrame should fail with a clear message."""
        from src.soc_calculator import validate_dataframe
        df = pd.DataFrame({"temperature": [25.0], "humidity": [80.0]})
        with pytest.raises(ValueError, match="missing required columns"):
            validate_dataframe(df)

    def test_non_numeric_column_raises(self):
        from src.soc_calculator import validate_dataframe
        bad_df = VALID_DF.copy()
        bad_df = bad_df.assign(bulk_density_g_cm3=["a", "b", "c"])
        with pytest.raises(ValueError, match="numeric"):
            validate_dataframe(bad_df)

    def test_non_dataframe_input_raises(self):
        from src.soc_calculator import validate_dataframe
        with pytest.raises(TypeError):
            validate_dataframe({"bulk_density_g_cm3": [1.2]})  # type: ignore[arg-type]

    def test_none_input_raises(self):
        from src.soc_calculator import validate_dataframe
        with pytest.raises(TypeError):
            validate_dataframe(None)  # type: ignore[arg-type]

    def test_dataframe_with_extra_columns_passes(self):
        """Additional columns beyond the required set should be accepted."""
        from src.soc_calculator import validate_dataframe
        df_extra = VALID_DF.copy()
        df_extra = df_extra.assign(land_use=["forest", "cropland", "grassland"])
        validate_dataframe(df_extra)  # should not raise

    def test_single_row_dataframe_passes(self):
        from src.soc_calculator import validate_dataframe
        df_one = pd.DataFrame([{"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 2.5, "depth_cm": 30}])
        validate_dataframe(df_one)  # should not raise


# ===========================================================================
# 4. Data loading from CSV
# ===========================================================================

class TestLoadData:
    """Tests for SoilCarbonEstimator.load_data."""

    def test_load_sample_csv(self):
        """Demo CSV loads to a non-empty DataFrame with expected columns."""
        from src.main import SoilCarbonEstimator
        estimator = SoilCarbonEstimator()
        df = estimator.load_data(str(SAMPLE_CSV))
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_sample_csv_has_required_columns(self):
        from src.main import SoilCarbonEstimator
        df = SoilCarbonEstimator().load_data(str(SAMPLE_CSV))
        for col in ("bulk_density_g_cm3", "organic_carbon_pct", "depth_cm"):
            assert col in df.columns, f"Column '{col}' missing from sample CSV"

    def test_sample_csv_row_count(self):
        """Demo file should have exactly 20 data rows."""
        from src.main import SoilCarbonEstimator
        df = SoilCarbonEstimator().load_data(str(SAMPLE_CSV))
        assert len(df) == 20

    def test_load_nonexistent_file_raises(self):
        from src.main import SoilCarbonEstimator
        with pytest.raises(FileNotFoundError):
            SoilCarbonEstimator().load_data("/nonexistent/path/data.csv")

    def test_load_unsupported_extension_raises(self):
        from src.main import SoilCarbonEstimator
        with pytest.raises(ValueError, match="Unsupported file extension"):
            SoilCarbonEstimator().load_data("/tmp/data.parquet")

    def test_load_does_not_mutate_filesystem(self, tmp_path):
        """Calling load_data should not create or modify any files."""
        from src.main import SoilCarbonEstimator
        csv_file = tmp_path / "test.csv"
        VALID_DF.to_csv(csv_file, index=False)
        mtime_before = csv_file.stat().st_mtime
        SoilCarbonEstimator().load_data(str(csv_file))
        assert csv_file.stat().st_mtime == mtime_before

    def test_load_returns_correct_dtypes(self, tmp_path):
        """Numeric columns loaded from CSV should be numeric dtype."""
        from src.main import SoilCarbonEstimator
        csv_file = tmp_path / "typed.csv"
        VALID_DF.to_csv(csv_file, index=False)
        df = SoilCarbonEstimator().load_data(str(csv_file))
        assert pd.api.types.is_numeric_dtype(df["bulk_density_g_cm3"])
        assert pd.api.types.is_numeric_dtype(df["organic_carbon_pct"])
        assert pd.api.types.is_numeric_dtype(df["depth_cm"])


# ===========================================================================
# 5. add_soc_stock_column immutability and correctness
# ===========================================================================

class TestAddSOCStockColumn:
    """Tests for soc_calculator.add_soc_stock_column."""

    def test_returns_new_dataframe(self):
        """The original DataFrame must not be modified."""
        from src.soc_calculator import add_soc_stock_column
        original_cols = list(VALID_DF.columns)
        result = add_soc_stock_column(VALID_DF)
        assert list(VALID_DF.columns) == original_cols
        assert "soc_stock_tC_ha" in result.columns

    def test_soc_stock_values_are_positive(self):
        from src.soc_calculator import add_soc_stock_column
        result = add_soc_stock_column(VALID_DF)
        assert (result["soc_stock_tC_ha"] > 0).all()

    def test_nan_row_yields_nan_soc(self):
        """A row with a NaN in a required column should produce NaN, not raise."""
        from src.soc_calculator import add_soc_stock_column
        df_with_nan = pd.DataFrame([
            {"bulk_density_g_cm3": np.nan, "organic_carbon_pct": 2.5, "depth_cm": 30},
            {"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 2.5, "depth_cm": 30},
        ])
        result = add_soc_stock_column(df_with_nan)
        assert math.isnan(result["soc_stock_tC_ha"].iloc[0])
        assert not math.isnan(result["soc_stock_tC_ha"].iloc[1])

    def test_out_of_range_row_yields_nan(self):
        """A row with bulk_density > MAX should produce NaN in the output column."""
        from src.soc_calculator import add_soc_stock_column
        df_bad = pd.DataFrame([
            {"bulk_density_g_cm3": 9.9, "organic_carbon_pct": 2.5, "depth_cm": 30},
        ])
        result = add_soc_stock_column(df_bad)
        assert math.isnan(result["soc_stock_tC_ha"].iloc[0])

    def test_original_column_count_unchanged(self):
        """The original DataFrame must keep the same number of columns."""
        from src.soc_calculator import add_soc_stock_column
        n_cols_before = len(VALID_DF.columns)
        add_soc_stock_column(VALID_DF)
        assert len(VALID_DF.columns) == n_cols_before

    def test_output_has_one_extra_column(self):
        """Result should have exactly one more column than input."""
        from src.soc_calculator import add_soc_stock_column
        result = add_soc_stock_column(VALID_DF)
        assert len(result.columns) == len(VALID_DF.columns) + 1

    def test_values_match_manual_formula(self):
        """Row-level SOC values must match the hand-computed formula."""
        from src.soc_calculator import add_soc_stock_column
        result = add_soc_stock_column(VALID_DF)
        for _, row in result.iterrows():
            expected = round(
                row["bulk_density_g_cm3"] * (row["organic_carbon_pct"] / 100) * row["depth_cm"] * 100, 2
            )
            assert row["soc_stock_tC_ha"] == pytest.approx(expected, rel=1e-4)

    def test_empty_dataframe_raises(self):
        """An empty input must propagate through validate_dataframe."""
        from src.soc_calculator import add_soc_stock_column
        with pytest.raises(ValueError):
            add_soc_stock_column(pd.DataFrame())


# ===========================================================================
# 6. SoilCarbonEstimator.preprocess
# ===========================================================================

class TestPreprocess:
    """Tests for SoilCarbonEstimator.preprocess."""

    def test_column_names_lowercased(self):
        from src.main import SoilCarbonEstimator
        raw = pd.DataFrame({"BULK_DENSITY_G_CM3": [1.2], "ORGANIC_CARBON_PCT": [2.5], "DEPTH_CM": [30]})
        result = SoilCarbonEstimator().preprocess(raw)
        assert "bulk_density_g_cm3" in result.columns
        assert "organic_carbon_pct" in result.columns
        assert "depth_cm" in result.columns

    def test_spaces_replaced_with_underscores(self):
        from src.main import SoilCarbonEstimator
        raw = pd.DataFrame({"Bulk Density": [1.2], "SOC Pct": [2.5]})
        result = SoilCarbonEstimator().preprocess(raw)
        assert "bulk_density" in result.columns
        assert "soc_pct" in result.columns

    def test_leading_trailing_whitespace_stripped(self):
        from src.main import SoilCarbonEstimator
        raw = pd.DataFrame({" depth_cm ": [30], " organic_carbon_pct ": [2.5], " bulk_density_g_cm3 ": [1.2]})
        result = SoilCarbonEstimator().preprocess(raw)
        for col in result.columns:
            assert col == col.strip(), f"Column '{col}' still has surrounding whitespace"

    def test_all_nan_rows_dropped(self):
        from src.main import SoilCarbonEstimator
        raw = pd.DataFrame({
            "bulk_density_g_cm3": [1.2, np.nan],
            "organic_carbon_pct": [2.5, np.nan],
            "depth_cm": [30, np.nan],
        })
        result = SoilCarbonEstimator().preprocess(raw)
        assert len(result) == 1

    def test_does_not_mutate_input(self):
        from src.main import SoilCarbonEstimator
        original_cols = list(VALID_DF.columns)
        SoilCarbonEstimator().preprocess(VALID_DF)
        assert list(VALID_DF.columns) == original_cols

    def test_partial_nan_rows_preserved(self):
        """Rows with only some NaN values should NOT be dropped."""
        from src.main import SoilCarbonEstimator
        raw = pd.DataFrame({
            "bulk_density_g_cm3": [1.2, 1.1],
            "organic_carbon_pct": [2.5, np.nan],
            "depth_cm": [30, 20],
        })
        result = SoilCarbonEstimator().preprocess(raw)
        assert len(result) == 2  # partial-NaN row is kept


# ===========================================================================
# 7. SoilCarbonEstimator.analyze
# ===========================================================================

class TestAnalyze:
    """Tests for SoilCarbonEstimator.analyze."""

    def test_analyze_returns_required_keys(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        for key in ("total_records", "columns", "missing_pct"):
            assert key in result

    def test_analyze_includes_soc_stats_when_columns_present(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        assert "soc_stats" in result
        assert result["soc_stats"]["n_valid"] == len(VALID_DF)

    def test_analyze_does_not_mutate_input(self):
        """analyze() must not add columns to the caller's DataFrame."""
        from src.main import SoilCarbonEstimator
        df_copy = VALID_DF.copy()
        original_cols = list(df_copy.columns)
        SoilCarbonEstimator().analyze(df_copy)
        assert list(df_copy.columns) == original_cols

    def test_analyze_total_records(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        assert result["total_records"] == len(VALID_DF)

    def test_analyze_empty_dataframe_raises(self):
        from src.main import SoilCarbonEstimator
        with pytest.raises(ValueError):
            SoilCarbonEstimator().analyze(pd.DataFrame())

    def test_analyze_normalises_column_names(self):
        """Input column names are lower-cased; computed columns keep their casing."""
        from src.main import SoilCarbonEstimator
        df_messy = pd.DataFrame({
            "Bulk_Density_G_Cm3": [1.2],
            "Organic_Carbon_Pct": [2.5],
            "Depth_Cm": [30],
        })
        result = SoilCarbonEstimator().analyze(df_messy)
        assert "bulk_density_g_cm3" in result["columns"]
        assert "organic_carbon_pct" in result["columns"]
        assert "depth_cm" in result["columns"]

    def test_analyze_missing_pct_all_zeros_for_clean_data(self):
        """Clean data should report 0.0% missing for all columns."""
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        for col, pct in result["missing_pct"].items():
            if col != "soc_stock_tC_ha":
                assert pct == 0.0, f"Expected 0% missing for '{col}', got {pct}%"

    def test_analyze_soc_stats_keys(self):
        """soc_stats dict must contain all expected keys."""
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        for key in ("mean_tC_ha", "min_tC_ha", "max_tC_ha", "total_tC_ha", "n_valid"):
            assert key in result["soc_stats"]

    def test_analyze_without_soc_columns_no_soc_stats(self):
        """DataFrames without SOC columns should not include soc_stats key."""
        from src.main import SoilCarbonEstimator
        df_no_soc = pd.DataFrame({"temperature": [25.0, 26.0], "humidity": [80.0, 75.0]})
        result = SoilCarbonEstimator().analyze(df_no_soc)
        assert "soc_stats" not in result

    def test_analyze_drop_invalid_rows_false(self):
        """Setting drop_invalid_rows=False should keep out-of-range rows."""
        from src.main import SoilCarbonEstimator
        df_with_bad = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": -1.0, "organic_carbon_pct": 2.5, "depth_cm": 30}]),
        ], ignore_index=True)
        estimator = SoilCarbonEstimator(config={"drop_invalid_rows": False})
        result = estimator.analyze(df_with_bad)
        # All rows are kept (invalid row yields NaN, counted in total_records)
        assert result["total_records"] == len(VALID_DF) + 1

    def test_analyze_includes_summary_stats(self):
        """Results for numeric DataFrames must include summary_stats key."""
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        assert "summary_stats" in result

    def test_analyze_includes_means_and_totals(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().analyze(VALID_DF)
        assert "means" in result
        assert "totals" in result


# ===========================================================================
# 8. Full pipeline via SoilCarbonEstimator.run
# ===========================================================================

class TestRunPipeline:
    """Integration tests for SoilCarbonEstimator.run."""

    def test_run_on_sample_csv(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().run(str(SAMPLE_CSV))
        assert result["total_records"] == 20
        assert "soc_stats" in result

    def test_run_soc_stats_mean_positive(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().run(str(SAMPLE_CSV))
        assert result["soc_stats"]["mean_tC_ha"] > 0

    def test_run_missing_file_raises(self):
        from src.main import SoilCarbonEstimator
        with pytest.raises(FileNotFoundError):
            SoilCarbonEstimator().run("/no/such/file.csv")

    def test_run_returns_expected_soc_mean(self):
        """The pipeline mean SOC should be close to the hand-computed value."""
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().run(str(SAMPLE_CSV))
        # Based on demo/sample_data.csv corrected values
        assert result["soc_stats"]["mean_tC_ha"] == pytest.approx(75.86, rel=0.01)

    def test_run_returns_dict(self):
        from src.main import SoilCarbonEstimator
        result = SoilCarbonEstimator().run(str(SAMPLE_CSV))
        assert isinstance(result, dict)

    def test_run_on_tmp_csv(self, tmp_path):
        """Pipeline should work end-to-end on an arbitrary temporary CSV."""
        from src.main import SoilCarbonEstimator
        csv_file = tmp_path / "tmp_soil.csv"
        VALID_DF.to_csv(csv_file, index=False)
        result = SoilCarbonEstimator().run(str(csv_file))
        assert result["total_records"] == len(VALID_DF)
        assert "soc_stats" in result


# ===========================================================================
# 9. filter_valid_rows
# ===========================================================================

class TestFilterValidRows:
    """Tests for soc_calculator.filter_valid_rows."""

    def test_all_valid_rows_retained(self):
        from src.soc_calculator import filter_valid_rows
        result = filter_valid_rows(VALID_DF)
        assert len(result) == len(VALID_DF)

    def test_negative_bulk_density_row_dropped(self):
        from src.soc_calculator import filter_valid_rows
        df_with_bad = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": -1.0, "organic_carbon_pct": 2.5, "depth_cm": 30}]),
        ], ignore_index=True)
        result = filter_valid_rows(df_with_bad)
        assert len(result) == len(VALID_DF)

    def test_over_100_pct_oc_row_dropped(self):
        from src.soc_calculator import filter_valid_rows
        df_with_bad = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 105.0, "depth_cm": 30}]),
        ], ignore_index=True)
        result = filter_valid_rows(df_with_bad)
        assert len(result) == len(VALID_DF)

    def test_original_not_mutated(self):
        from src.soc_calculator import filter_valid_rows
        df_with_bad = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": -0.5, "organic_carbon_pct": 2.5, "depth_cm": 30}]),
        ], ignore_index=True)
        length_before = len(df_with_bad)
        filter_valid_rows(df_with_bad)
        assert len(df_with_bad) == length_before

    def test_nan_row_dropped(self):
        from src.soc_calculator import filter_valid_rows
        df_with_nan = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": np.nan, "organic_carbon_pct": 2.5, "depth_cm": 30}]),
        ], ignore_index=True)
        result = filter_valid_rows(df_with_nan)
        assert len(result) == len(VALID_DF)

    def test_zero_depth_row_dropped(self):
        """depth_cm <= 0 should be excluded."""
        from src.soc_calculator import filter_valid_rows
        df_with_zero_depth = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 2.5, "depth_cm": 0}]),
        ], ignore_index=True)
        result = filter_valid_rows(df_with_zero_depth)
        assert len(result) == len(VALID_DF)

    def test_depth_exceeds_max_row_dropped(self):
        from src.soc_calculator import filter_valid_rows
        df_deep = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 2.5, "depth_cm": 500}]),
        ], ignore_index=True)
        result = filter_valid_rows(df_deep)
        assert len(result) == len(VALID_DF)

    def test_returns_copy_not_view(self):
        """The returned DataFrame should be a copy, not a view of the original."""
        from src.soc_calculator import filter_valid_rows
        result = filter_valid_rows(VALID_DF)
        assert result is not VALID_DF

    def test_empty_dataframe_raises(self):
        from src.soc_calculator import filter_valid_rows
        with pytest.raises(ValueError):
            filter_valid_rows(pd.DataFrame())


# ===========================================================================
# 10. SoilCarbonEstimator.to_dataframe
# ===========================================================================

class TestToDataFrame:
    """Tests for SoilCarbonEstimator.to_dataframe."""

    def test_returns_dataframe(self):
        from src.main import SoilCarbonEstimator
        estimator = SoilCarbonEstimator()
        result = estimator.analyze(VALID_DF)
        df_out = estimator.to_dataframe(result)
        assert isinstance(df_out, pd.DataFrame)

    def test_output_has_metric_and_value_columns(self):
        from src.main import SoilCarbonEstimator
        estimator = SoilCarbonEstimator()
        result = estimator.analyze(VALID_DF)
        df_out = estimator.to_dataframe(result)
        assert "metric" in df_out.columns
        assert "value" in df_out.columns

    def test_nested_dicts_expanded(self):
        """Nested dict entries should appear as 'parent.child' metric names."""
        from src.main import SoilCarbonEstimator
        estimator = SoilCarbonEstimator()
        result = estimator.analyze(VALID_DF)
        df_out = estimator.to_dataframe(result)
        dot_metrics = [m for m in df_out["metric"] if "." in m]
        assert len(dot_metrics) > 0

    def test_scalar_values_preserved(self):
        """Top-level scalar values should appear verbatim."""
        from src.main import SoilCarbonEstimator
        estimator = SoilCarbonEstimator()
        result = estimator.analyze(VALID_DF)
        df_out = estimator.to_dataframe(result)
        total_records_rows = df_out[df_out["metric"] == "total_records"]
        assert len(total_records_rows) == 1
        assert total_records_rows["value"].iloc[0] == len(VALID_DF)

    def test_does_not_mutate_input_dict(self):
        """to_dataframe must not add or remove keys from the result dict."""
        from src.main import SoilCarbonEstimator
        estimator = SoilCarbonEstimator()
        result = estimator.analyze(VALID_DF)
        keys_before = set(result.keys())
        estimator.to_dataframe(result)
        assert set(result.keys()) == keys_before


# ===========================================================================
# 11. Data generator
# ===========================================================================

class TestDataGenerator:
    """Tests for data_generator.generate_sample."""

    def test_generate_sample_returns_dataframe(self):
        from src.data_generator import generate_sample
        df = generate_sample(10)
        assert isinstance(df, pd.DataFrame)

    def test_generate_sample_row_count(self):
        from src.data_generator import generate_sample
        df = generate_sample(50)
        assert len(df) == 50

    def test_generate_sample_has_expected_columns(self):
        from src.data_generator import generate_sample, COLUMNS
        df = generate_sample(10)
        for col in COLUMNS:
            assert col in df.columns, f"Expected column '{col}' missing"

    def test_generate_sample_reproducible(self):
        """Same seed should produce identical DataFrames."""
        from src.data_generator import generate_sample
        df1 = generate_sample(20, seed=99)
        df2 = generate_sample(20, seed=99)
        pd.testing.assert_frame_equal(df1, df2)

    def test_generate_sample_different_seeds_differ(self):
        """Different seeds should produce different data."""
        from src.data_generator import generate_sample
        df1 = generate_sample(20, seed=1)
        df2 = generate_sample(20, seed=2)
        assert not df1.equals(df2)

    def test_generate_sample_invalid_n_raises(self):
        """Non-positive n must raise ValueError."""
        from src.data_generator import generate_sample
        with pytest.raises(ValueError):
            generate_sample(0)
        with pytest.raises(ValueError):
            generate_sample(-5)

    def test_generate_sample_does_not_mutate_args(self):
        """generate_sample has no mutable arguments, but calling it twice
        with the same seed should return two independent DataFrames."""
        from src.data_generator import generate_sample
        df1 = generate_sample(10, seed=42)
        df1_cols = list(df1.columns)
        df2 = generate_sample(10, seed=42)
        assert list(df2.columns) == df1_cols

    def test_generate_sample_land_use_valid_values(self):
        """land_use column should only contain known land-use category strings."""
        from src.data_generator import generate_sample, LAND_USE_CHOICES
        df = generate_sample(50)
        assert set(df["land_use"]).issubset(set(LAND_USE_CHOICES))

    def test_generate_sample_no_null_values(self):
        """Generated data should be free of null values."""
        from src.data_generator import generate_sample
        df = generate_sample(30)
        assert not df.isnull().any().any()


# ===========================================================================
# 12. Module-level constants
# ===========================================================================

class TestSOCCalculatorConstants:
    """Sanity checks for physical constants defined in soc_calculator."""

    def test_max_bulk_density_positive(self):
        from src.soc_calculator import MAX_BULK_DENSITY
        assert MAX_BULK_DENSITY > 0

    def test_max_bulk_density_reasonable(self):
        """Quartz density (~2.65 g/cm3) is the accepted upper bound."""
        from src.soc_calculator import MAX_BULK_DENSITY
        assert 2.0 <= MAX_BULK_DENSITY <= 3.0

    def test_max_percent_is_100(self):
        from src.soc_calculator import MAX_PERCENT
        assert MAX_PERCENT == 100.0

    def test_max_depth_cm_positive(self):
        from src.soc_calculator import MAX_DEPTH_CM
        assert MAX_DEPTH_CM > 0

    def test_required_columns_is_set(self):
        from src.soc_calculator import REQUIRED_COLUMNS
        assert isinstance(REQUIRED_COLUMNS, (set, frozenset))
        assert "bulk_density_g_cm3" in REQUIRED_COLUMNS
        assert "organic_carbon_pct" in REQUIRED_COLUMNS
        assert "depth_cm" in REQUIRED_COLUMNS
