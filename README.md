# Soil Carbon Estimator

Soil organic carbon (SOC) stock estimation and monitoring tools for tropical and subtropical sites.

## Features

- Data ingestion from CSV or Excel files
- Automated SOC stock calculation (tC/ha) using the standard bulk-density formula
- Input validation with clear error messages for out-of-range and missing values
- Summary statistics and trend reporting
- Sample data for demo and testing purposes
- Comprehensive test suite (pytest)

## Installation

```bash
pip install -r requirements.txt
```

For running tests, also install pytest:

```bash
pip install pytest
```

## Quick Start

### 1. Run the full pipeline on the included demo data

```python
from src.main import SoilCarbonEstimator

estimator = SoilCarbonEstimator()
result = estimator.run("demo/sample_data.csv")

print(f"Records processed : {result['total_records']}")
print(f"Mean SOC stock    : {result['soc_stats']['mean_tC_ha']:.2f} tC/ha")
print(f"Total SOC stock   : {result['soc_stats']['total_tC_ha']:.2f} tC/ha")
```

### 2. Load, validate, and analyse your own CSV

```python
import pandas as pd
from src.main import SoilCarbonEstimator

estimator = SoilCarbonEstimator()

# Load data
df = estimator.load_data("your_data.csv")

# Validate and analyse
result = estimator.analyze(df)

# Export flat metrics table
metrics_df = estimator.to_dataframe(result)
metrics_df.to_csv("output/metrics.csv", index=False)
```

### 3. Calculate a single SOC stock value

```python
from src.soc_calculator import calculate_soc_stock

# bulk_density_g_cm3, organic_carbon_pct, depth_cm
stock = calculate_soc_stock(1.12, 2.85, 30)
print(f"SOC stock: {stock} tC/ha")
# SOC stock: 9576.0 tC/ha
```

### 4. Add computed SOC stock to an existing DataFrame

```python
import pandas as pd
from src.soc_calculator import add_soc_stock_column

df = pd.read_csv("demo/sample_data.csv")
enriched = add_soc_stock_column(df)   # returns a new DataFrame, original unchanged
print(enriched[["site_id", "soc_stock_tC_ha"]].head())
```

## Data Format

### Required columns for SOC stock calculation

| Column | Type | Description |
|---|---|---|
| `bulk_density_g_cm3` | float | Soil bulk density (g/cm3), range 0–2.65 |
| `organic_carbon_pct` | float | Organic carbon content (%), range 0–100 |
| `depth_cm` | float | Sampling depth (cm), range 0–300 |

### Additional columns recognised in demo data

| Column | Type | Description |
|---|---|---|
| `site_id` | str | Unique site identifier |
| `latitude` | float | Decimal degrees (WGS84) |
| `longitude` | float | Decimal degrees (WGS84) |
| `clay_pct` | float | Clay fraction (%) |
| `land_use` | str | Land-use category |
| `sampling_date` | str | ISO 8601 date string |
| `soc_stock_tC_ha` | float | Pre-computed reference SOC stock |

## Sample Data

The file `demo/sample_data.csv` contains 20 realistic rows representing tropical and subtropical soil sampling sites across Java, Indonesia.  Site IDs follow the pattern `TH001`–`TH020`.

Land-use categories present: `tropical_forest`, `agroforestry`, `cropland`, `grassland`, `peatland`, `bare_soil`.

Values were constructed to reflect published literature ranges:

- Bulk density: 1.05–1.42 g/cm3
- Organic carbon: 0.98–4.12 %
- Sampling depth: 20 or 30 cm
- SOC stock: ~40–125 tC/ha

### Preview

```
site_id  lat      lon       depth_cm  bulk_density  organic_carbon_pct  land_use         soc_stock_tC_ha
TH001    -6.2145  106.8451  30        1.12          2.85                tropical_forest  96.12
TH002    -6.3012  106.9102  30        1.08          3.41                tropical_forest  110.48
TH003    -6.1887  106.7923  20        1.25          1.92                cropland         48.00
```

## Project Structure

```
soil-carbon-estimator/
├── src/
│   ├── __init__.py
│   ├── main.py            # SoilCarbonEstimator class (pipeline entry point)
│   ├── soc_calculator.py  # Pure calculation and validation functions
│   └── data_generator.py  # Synthetic data generator for development
├── tests/
│   └── test_estimator.py  # Pytest test suite (30+ assertions, 8+ test functions)
├── demo/
│   └── sample_data.csv    # 20-row realistic tropical soil dataset
├── data/                  # Drop your own data files here (gitignored)
├── examples/
│   └── basic_usage.py     # Runnable usage examples
├── requirements.txt
├── CHANGELOG.md
└── README.md
```

## Running Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pip install pytest-cov
pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected output (abbreviated):

```
tests/test_estimator.py::TestCalculateSOCStock::test_basic_calculation PASSED
tests/test_estimator.py::TestCalculateSOCStock::test_zero_organic_carbon_returns_zero PASSED
...
================================ 30 passed in 1.23s ================================
```

## Input Validation

The library validates all inputs at system boundaries:

- Negative values for bulk density, organic carbon, or depth raise `ValueError`.
- Percentages above 100 raise `ValueError`.
- Depth values above 300 cm raise `ValueError`.
- Non-numeric data in required columns raises `ValueError`.
- Missing files raise `FileNotFoundError`.
- Non-CSV/Excel extensions raise `ValueError`.

All data-transformation functions return new objects and never mutate inputs.

## License

MIT License — free to use, modify, and distribute.
