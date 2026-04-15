"""
SOC stock calculation utilities for the soil carbon estimator.

Provides pure functions for computing soil organic carbon (SOC) stocks
from field measurements, following immutable data patterns.

Author: github.com/achmadnaufal
"""
from typing import Optional
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {
    "bulk_density_g_cm3",
    "organic_carbon_pct",
    "depth_cm",
}

VALID_LAND_USES = {
    "tropical_forest",
    "agroforestry",
    "cropland",
    "grassland",
    "peatland",
    "bare_soil",
}

MAX_PERCENT = 100.0
MIN_BULK_DENSITY = 0.0
MAX_BULK_DENSITY = 2.65  # g/cm3 — approximate density of quartz (upper physical limit)
MAX_DEPTH_CM = 300.0     # 3 metres is a practical upper limit for field campaigns


# ---------------------------------------------------------------------------
# Calculation helpers
# ---------------------------------------------------------------------------


def calculate_soc_stock(
    bulk_density_g_cm3: float,
    organic_carbon_pct: float,
    depth_cm: float,
) -> float:
    """Calculate SOC stock in tonnes of carbon per hectare (tC/ha).

    Uses the standard formula::

        SOC_stock (tC/ha) = bulk_density (g/cm3)
                            × (organic_carbon_pct / 100)
                            × depth (cm)
                            × 100

    Dividing OC% by 100 converts from percentage to fraction; the
    remaining factor of 100 converts from g/cm2 to tC/ha.

    Parameters
    ----------
    bulk_density_g_cm3:
        Soil bulk density in grams per cubic centimetre.  Must be > 0.
    organic_carbon_pct:
        Organic carbon content expressed as a percentage (0–100).
    depth_cm:
        Sampling depth in centimetres.  Must be > 0.

    Returns
    -------
    float
        SOC stock in tC/ha, rounded to two decimal places.

    Raises
    ------
    ValueError
        If any parameter is negative, zero where not permitted, or
        outside its valid physical range.

    Examples
    --------
    >>> calculate_soc_stock(1.2, 2.5, 30)
    90.0

    The factor of 100 converts g/cm2 to tC/ha, while dividing OC% by 100
    converts percentage to a fraction.
    """
    _validate_soc_inputs(bulk_density_g_cm3, organic_carbon_pct, depth_cm)
    stock = bulk_density_g_cm3 * (organic_carbon_pct / 100) * depth_cm * 100
    return round(stock, 2)


def _validate_soc_inputs(
    bulk_density_g_cm3: float,
    organic_carbon_pct: float,
    depth_cm: float,
) -> None:
    """Raise ValueError for any out-of-range SOC input value.

    Parameters
    ----------
    bulk_density_g_cm3:
        Soil bulk density in g/cm3.
    organic_carbon_pct:
        Organic carbon percentage (0–100).
    depth_cm:
        Depth in centimetres (> 0).

    Raises
    ------
    ValueError
        Descriptive message indicating which parameter failed and why.
    """
    if bulk_density_g_cm3 < 0:
        raise ValueError(
            f"bulk_density_g_cm3 must be >= 0, got {bulk_density_g_cm3}"
        )
    if bulk_density_g_cm3 > MAX_BULK_DENSITY:
        raise ValueError(
            f"bulk_density_g_cm3 {bulk_density_g_cm3} exceeds physical maximum "
            f"of {MAX_BULK_DENSITY} g/cm3"
        )
    if organic_carbon_pct < 0:
        raise ValueError(
            f"organic_carbon_pct must be >= 0, got {organic_carbon_pct}"
        )
    if organic_carbon_pct > MAX_PERCENT:
        raise ValueError(
            f"organic_carbon_pct must be <= {MAX_PERCENT}, got {organic_carbon_pct}"
        )
    if depth_cm <= 0:
        raise ValueError(f"depth_cm must be > 0, got {depth_cm}")
    if depth_cm > MAX_DEPTH_CM:
        raise ValueError(
            f"depth_cm {depth_cm} exceeds maximum supported depth of {MAX_DEPTH_CM} cm"
        )


# ---------------------------------------------------------------------------
# DataFrame-level helpers
# ---------------------------------------------------------------------------


def validate_dataframe(df: pd.DataFrame) -> None:
    """Check that *df* contains all required columns with valid data types.

    Parameters
    ----------
    df:
        DataFrame to validate.

    Raises
    ------
    ValueError
        If required columns are missing, the DataFrame is empty, or
        numeric columns contain non-numeric data.
    TypeError
        If *df* is not a :class:`pandas.DataFrame`.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected a pandas DataFrame, got {type(df).__name__}")
    if df.empty:
        raise ValueError("DataFrame is empty — no rows to process")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"DataFrame is missing required columns: {sorted(missing)}"
        )

    for col in REQUIRED_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(
                f"Column '{col}' must be numeric, but contains non-numeric data"
            )


def add_soc_stock_column(df: pd.DataFrame) -> pd.DataFrame:
    """Return a new DataFrame with a ``soc_stock_tC_ha`` column appended.

    This function never mutates the input DataFrame.  Rows with missing
    values in any required column are set to ``NaN`` in the output column.

    Parameters
    ----------
    df:
        Input DataFrame.  Must contain ``bulk_density_g_cm3``,
        ``organic_carbon_pct``, and ``depth_cm`` columns.

    Returns
    -------
    pd.DataFrame
        A copy of *df* with the new ``soc_stock_tC_ha`` column.

    Raises
    ------
    ValueError
        Propagated from :func:`validate_dataframe`.

    Examples
    --------
    >>> import pandas as pd
    >>> data = {"bulk_density_g_cm3": [1.2], "organic_carbon_pct": [2.5], "depth_cm": [30]}
    >>> result = add_soc_stock_column(pd.DataFrame(data))
    >>> float(result["soc_stock_tC_ha"].iloc[0])
    90.0
    """
    validate_dataframe(df)
    result = df.copy()

    def _safe_calc(row: pd.Series) -> Optional[float]:
        if row[list(REQUIRED_COLUMNS)].isnull().any():
            return np.nan
        try:
            return calculate_soc_stock(
                row["bulk_density_g_cm3"],
                row["organic_carbon_pct"],
                row["depth_cm"],
            )
        except ValueError:
            return np.nan

    result["soc_stock_tC_ha"] = result.apply(_safe_calc, axis=1)
    return result


def filter_valid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *df* containing only rows that pass all range checks.

    Rows are excluded when any of the following conditions hold:

    * ``bulk_density_g_cm3`` is negative or exceeds ``MAX_BULK_DENSITY``
    * ``organic_carbon_pct`` is negative or exceeds 100
    * ``depth_cm`` is <= 0 or exceeds ``MAX_DEPTH_CM``
    * Any required column value is ``NaN``

    Parameters
    ----------
    df:
        Input DataFrame with the required numeric columns present.

    Returns
    -------
    pd.DataFrame
        Filtered copy — original index is preserved.
    """
    validate_dataframe(df)
    mask = (
        df["bulk_density_g_cm3"].between(0, MAX_BULK_DENSITY, inclusive="both")
        & df["organic_carbon_pct"].between(0, MAX_PERCENT, inclusive="both")
        & df["depth_cm"].between(0, MAX_DEPTH_CM, inclusive="neither")
        & df[list(REQUIRED_COLUMNS)].notna().all(axis=1)
    )
    return df.loc[mask].copy()
