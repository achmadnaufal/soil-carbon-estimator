# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.0] - 2026-04-16

### Added
- Unit tests with pytest covering all core modules (`tests/test_estimator.py`)
- Test classes for: SOC calculation, edge cases, DataFrame validation, data loading,
  `add_soc_stock_column` immutability, `analyze`, full pipeline, `filter_valid_rows`,
  and the data generator
- `demo/sample_data.csv` -- 20-row realistic tropical soil dataset for Indonesian sites
  (West Java / Central Java) with corrected SOC stock values
- Comprehensive docstrings and type hints across all public functions and classes
- Input validation and edge case handling (empty DataFrames, missing columns,
  negative values, NaN handling, out-of-range physical values)
- Immutable data patterns throughout -- all transformation functions return new
  objects and never mutate their inputs
- `data_generator.py` refactored: private helper `_generate_date_column`, added
  `ValueError` guard for non-positive `n`, full docstrings, and type annotations

### Changed
- `demo/sample_data.csv` SOC stock values corrected to match the formula
  `BD * (OC% / 100) * depth * 100` (rows TH001, TH013, TH015, TH017, TH018)
- README expanded with badges, Quick Start, Sample Output table, Running Tests
  section, required columns reference table, and Project Structure tree

### Fixed
- Incorrect pre-computed `soc_stock_tC_ha` values in `demo/sample_data.csv`

## [0.1.0] - Initial Release

### Added
- Core soil organic carbon estimation functionality (`src/soc_calculator.py`)
- `SoilCarbonEstimator` pipeline class (`src/main.py`) with load, validate,
  preprocess, analyze, and export methods
- Synthetic data generator (`src/data_generator.py`)
- CSV and Excel file loading support
- SOC formula: `BD (g/cm3) * (OC% / 100) * depth (cm) * 100 = tC/ha`
- Physical range validation (bulk density, organic carbon percentage, depth)
- Column name normalisation (lowercase, strip whitespace, replace spaces)
- `filter_valid_rows` to drop out-of-range measurements before analysis
- `requirements.txt` with pandas, NumPy, SciPy, Rich, and pytest dependencies
