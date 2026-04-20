# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - 2026-04-21

### Added
- `src/soc_saturation.py` — new module implementing the Hassink (1997)
  pedotransfer function for SOC saturation capacity and deficit, with
  an alternative Six et al. (2002) coefficient set.  Public API:
  - `calculate_c_saturation()`: linear pedotransfer `C_sat = a + b*(clay+silt)`
    returning g C / kg whole soil.
  - `c_sat_stock_tC_ha()`: convert saturation concentration to a per-hectare
    stock for a specified layer thickness and bulk density.
  - `calculate_saturation()`: high-level wrapper returning an immutable
    `SaturationResult` with saturation stock, deficit (clipped at zero),
    and saturation ratio.
  - Frozen `SaturationInputs` / `SaturationResult` dataclasses and a
    `with_method()` helper for method swapping without mutation.
  - Batch helpers `validate_saturation_dataframe()`,
    `add_saturation_columns()`, and `summarise_saturation()` for
    DataFrame-scale workflows, with NaN-safe row handling.
  - Full input validation (clay/silt in 0–100, clay+silt ≤ 100,
    BD within 0.1–2.65 g/cm3, depth > 0 and ≤ 300 cm) with descriptive
    `ValueError` / `TypeError` messages.
- `tests/test_soc_saturation.py` — 46 pytest tests covering the
  pedotransfer equation, method switching, stock conversion,
  supersaturation clipping, immutability of inputs and results,
  DataFrame batch paths, NaN handling, and a smoke test against the
  bundled sample data.
- `sample_data/soc_saturation_scenarios.csv` — 20-row realistic dataset
  spanning tropical forest, tropical cropland, agroforestry, savanna,
  temperate forest/grassland/cropland, boreal, andosol, vertisol,
  sandy/arid, and deep-layer (60 cm) profiles.
- README "SOC saturation deficit (Hassink 1997)" section with a
  single-profile example and a DataFrame batch example for MRV and
  carbon-farming feasibility analyses.

### Earlier additions still in Unreleased (CLI + plotting)
- `src/cli.py` — argparse-based command-line interface exposing four
  sub-commands for the most common analyst workflows:
  - `analyze` runs the full `SoilCarbonEstimator` pipeline on a CSV or
    Excel file and emits results to stdout or file in CSV (flattened
    metric/value) or JSON format.
  - `harmonise` integrates a long-format profile dataset to a reference
    depth (default 30 cm) using `harmonise_to_reference_depth`.
  - `stock-change` joins a baseline and a monitoring survey on
    `site_id` and emits per-site deltas or a one-row aggregate summary
    (requires `--years`).
  - `generate` writes a synthetic demo dataset using
    `data_generator.generate_sample` with a configurable row count and
    seed.
  - Friendly error handling: missing files and unsupported extensions
    return exit code 2 with a message on stderr rather than tracebacks.
- `src/plotting.py` — optional matplotlib-based visualisation helpers:
  - `plot_soc_histogram` for the distribution of SOC stock values.
  - `plot_soc_by_land_use` for a boxplot stratified by land-use class.
  - `plot_depth_profile` for a SOC-vs-depth line chart with an inverted
    y-axis (soil-science convention).  All helpers return
    `matplotlib.figure.Figure` objects; callers decide when/where to
    persist them.  matplotlib is imported lazily so the package remains
    usable when matplotlib is not installed.
- `tests/test_cli.py` — 8 pytest tests covering sub-command wiring,
  CSV/JSON output, error handling for missing files, the harmonise and
  stock-change flows end-to-end, and synthetic dataset generation.
- `tests/test_plotting.py` — 10 pytest tests covering histogram, boxplot,
  and depth-profile helpers including edge cases (empty DataFrame,
  missing columns, all-NaN columns, mismatched input lengths, negative
  depths) with `importorskip` for environments without matplotlib.
- `src/__init__.py` now re-exports `cli_main` for programmatic access.

### [Earlier additions still in Unreleased]
- `src/depth_profile.py` — new module for harmonising irregular SOC
  depth profiles to a reference depth (typical IPCC / FAO GSOC / Verra
  reporting requirement).  Public API:
  - `interpolate_soc_profile()`: resample per-horizon SOC stocks onto an
    arbitrary depth grid via linear interpolation; targets above /
    below the measured range are clamped (no silent extrapolation).
  - `integrate_soc_to_depth()`: cumulative SOC stock from surface to a
    target reference depth.  Within-range targets use linear
    interpolation of the cumulative-stock curve; beyond-range targets
    fit an exponential decay model (Bernoux 1998) and integrate
    analytically.  `extrapolate=False` raises a clear `ValueError`
    instead of fitting.
  - `harmonise_to_reference_depth()`: groupby-style helper that applies
    `integrate_soc_to_depth()` to each site in a long-format DataFrame
    and returns one harmonised row per site.
  - Comprehensive input validation (TypeError / ValueError) for empty
    profiles, NaN, negative depths/stocks, duplicate depths, depths
    above the 300 cm physical maximum, and non-numeric targets.
  - Strict immutability: every public function returns new objects and
    never mutates its inputs.
- `tests/test_depth_profile.py` — 43 pytest tests covering: happy path
  interpolation, target ordering, clamping above/below range,
  integration within / at / beyond measured horizons, exponential
  extrapolation monotonicity, single-horizon edge case, multi-site
  groupby harmonisation, custom column names, and full immutability
  invariants for all three public functions.
- `src/__init__.py` — package-level re-exports for the depth-profile
  helpers, the existing pipeline class, the SOC calculator helpers, and
  the stock-change utilities.
- README "New: Depth-Profile Harmonisation" section with a Quick Start
  example and a 3-step usage walkthrough (interpolate, integrate,
  harmonise) including the exponential-extrapolation note.

## [0.2.1] - 2026-04-17

### Added
- `src/stock_change_calculator.py` — new module for computing SOC stock
  change between two paired survey DataFrames.  Key features:
  - `compute_stock_change()`: inner-joins two survey DataFrames on a site
    identifier, computes per-site absolute delta (tC/ha), annualised accrual
    rate (tC/ha/yr), and 95 % confidence-interval bounds propagated from
    per-site measurement uncertainty (defaults to 5 % relative CV when no
    explicit error column is supplied).
  - `summarise_stock_change()`: aggregates per-site results into a frozen
    `StockChangeSummary` dataclass containing mean/total delta, mean annual
    rate, and a 95 % CI on the mean computed from the standard error of the
    site-level deltas.
  - Full input validation with descriptive `TypeError` / `ValueError`
    messages at every boundary; immutable outputs (returns new DataFrames
    and dataclasses, never mutates inputs).
- `tests/test_stock_change_calculator.py` — 28 pytest tests covering:
  happy path, immutability, inner-join behaviour, custom error columns,
  parametrized annual-rate checks across four time spans, single-site edge
  case, zero/negative `years_elapsed`, missing columns, no matching sites,
  and empty summary DataFrame.
- README "New: SOC Stock Change Calculator" section with a 4-step usage
  example including optional error-column usage and a note on inner-join
  semantics.

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
