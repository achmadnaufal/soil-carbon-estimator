"""Package: soil-carbon-estimator.

Public API re-exports for convenience.  Submodules can also be imported
directly (e.g. ``from src.depth_profile import integrate_soc_to_depth``).
"""
from src.soc_calculator import (  # noqa: F401
    REQUIRED_COLUMNS,
    add_soc_stock_column,
    calculate_soc_stock,
    filter_valid_rows,
    validate_dataframe,
)
from src.main import SoilCarbonEstimator  # noqa: F401
from src.stock_change_calculator import (  # noqa: F401
    StockChangeSummary,
    compute_stock_change,
    summarise_stock_change,
)
from src.depth_profile import (  # noqa: F401
    harmonise_to_reference_depth,
    integrate_soc_to_depth,
    interpolate_soc_profile,
)
from src.cli import main as cli_main  # noqa: F401

__all__ = [
    # SOC calculator
    "REQUIRED_COLUMNS",
    "add_soc_stock_column",
    "calculate_soc_stock",
    "filter_valid_rows",
    "validate_dataframe",
    # Pipeline
    "SoilCarbonEstimator",
    # Stock change
    "StockChangeSummary",
    "compute_stock_change",
    "summarise_stock_change",
    # Depth profile
    "harmonise_to_reference_depth",
    "integrate_soc_to_depth",
    "interpolate_soc_profile",
    # CLI
    "cli_main",
]
