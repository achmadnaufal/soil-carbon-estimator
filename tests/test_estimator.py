"""
Unit tests for the soil-carbon-estimator package.

Run with:  pytest tests/ -v

Coverage target: >= 80 %
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers – keep test fixtures immutable (no mutation)
# ---------------------------------------------------------------------------

SAMPLE_CSV = Path(__file__).parent.parent / "demo" / "sample_data.csv"

VALID_ROW = {
    "bulk_density_g_cm3": 1.2,
    "organic_carbon_pct": 2.5,
    "depth_cm": 30.0,
}

VALID_DF = pd.DataFrame([
    {"bulk_density_g_cm3": 1.2, "organic_carbon_pct": 2.5, "depth_cm": 30.0},
    {"bulk_density_g_cm3": 1.1, "organic_carbon_pct": 3.0, "depth_cm": 20.0},
    {"bulk_density_g_cm3": 1.35, "organic_carbon_pct": 1.5, "depth_cm": 30.0},
])


# ===========================================================================
# 1. SOC stock calculation – basic correctness
# ===========================================================================

class TestCalculateSOCStock:
    """Tests for soc_calculator.calculate_soc_stock."""

    def test_basic_calculation(self):
        """Standard mid-range inputs should return the expected value."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.2, 2.5, 30)
        # 1.2 × 2.5 × 30 × 100 = 9000  tC/ha … wait, unit check:
        # formula: BD(g/cm3) × OC(%) × depth(cm) × 100 → tC/ha
        assert result == pytest.approx(9000.0, rel=1e-4)

    def test_result_rounded_to_two_decimal_places(self):
        """Return value must be rounded to two decimal places."""
        from src.soc_calculator import calculate_soc_stock
        result = calculate_soc_stock(1.123456, 2.111111, 25)
        # verify it is rounded (at most 2 decimal digits)
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

    def test_realistic_tropical_site(self):
        """Values from demo/sample_data.csv row TH001 should match stored stock."""
        from src.soc_calculator import calculate_soc_stock
        # TH001: BD=1.12, OC=2.85, depth=30
        result = calculate_soc_stock(1.12, 2.85, 30)
        expected = 1.12 * 2.85 * 30 * 100
        assert result == pytest.approx(expected, rel=1e-4)


# ===========================================================================
# 2. SOC stock calculation – edge cases / invalid inputs
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


# ===========================================================================
# 3. Input validation – validate_dataframe
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


# ===========================================================================
# 5. add_soc_stock_column immutability
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


# ===========================================================================
# 6. SoilCarbonEstimator.analyze
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
        # The three input columns should be lower-cased
        assert "bulk_density_g_cm3" in result["columns"]
        assert "organic_carbon_pct" in result["columns"]
        assert "depth_cm" in result["columns"]


# ===========================================================================
# 7. Full pipeline via SoilCarbonEstimator.run
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


# ===========================================================================
# 8. filter_valid_rows
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
        assert len(df_with_bad) == length_before  # original unchanged

    def test_nan_row_dropped(self):
        from src.soc_calculator import filter_valid_rows
        df_with_nan = pd.concat([
            VALID_DF,
            pd.DataFrame([{"bulk_density_g_cm3": np.nan, "organic_carbon_pct": 2.5, "depth_cm": 30}]),
        ], ignore_index=True)
        result = filter_valid_rows(df_with_nan)
        assert len(result) == len(VALID_DF)
