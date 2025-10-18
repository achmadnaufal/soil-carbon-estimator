# Soil Carbon Estimator

Soil organic carbon (SOC) stock estimation and monitoring tools

## Features
- Data ingestion from CSV/Excel input files
- Automated analysis and KPI calculation
- Summary statistics and trend reporting
- Sample data generator for testing and development

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from src.main import SoilCarbonEstimator

analyzer = SoilCarbonEstimator()
df = analyzer.load_data("data/sample.csv")
result = analyzer.analyze(df)
print(result)
```

## Data Format

Expected CSV columns: `sample_id, depth_cm, bulk_density, soc_pct, clay_pct, land_use, plot_id`

## Project Structure

```
soil-carbon-estimator/
├── src/
│   ├── main.py          # Core analysis logic
│   └── data_generator.py # Sample data generator
├── data/                # Data directory (gitignored for real data)
├── examples/            # Usage examples
├── requirements.txt
└── README.md
```

## License

MIT License — free to use, modify, and distribute.
