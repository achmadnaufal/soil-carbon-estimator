"""
SOC saturation capacity and deficit calculations (Hassink 1997).

This module implements the Hassink (1997) pedotransfer function which relates
fine mineral particle content (clay + silt) to the physical capacity of a
soil to stabilise organic carbon.  The derived "saturation deficit" is the
additional SOC that a soil can theoretically accumulate before it reaches
its mineral-associated protection limit, and is widely used in MRV, carbon
farming, and Nature-based Solution (NbS) feasibility studies.

References
----------
Hassink, J. (1997). The capacity of soils to preserve organic C and N by
    their association with clay and silt particles.
    *Plant and Soil*, 191(1), 77-87.
Six, J., Conant, R. T., Paul, E. A., & Paustian, K. (2002). Stabilization
    mechanisms of soil organic matter: Implications for C-saturation of
    soils. *Plant and Soil*, 241(2), 155-176.

Author: github.com/achmadnaufal
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hassink 1997, eq. 4: C_sat (g C / kg soil) = 4.09 + 0.37 * (clay+silt %)
HASSINK_INTERCEPT_G_KG = 4.09
HASSINK_SLOPE_G_KG = 0.37

# Alternative coefficients reported in Six et al. 2002 Table 3 for the
# non-cultivated temperate dataset:  C_sat = 2.11 + 0.32 * (clay+silt %)
SIX_INTERCEPT_G_KG = 2.11
SIX_SLOPE_G_KG = 0.32

MIN_PCT = 0.0
MAX_PCT = 100.0
MIN_BULK_DENSITY = 0.1       # g/cm3 — organic peats can be ~0.1
MAX_BULK_DENSITY = 2.65      # g/cm3 — upper physical limit (quartz density)
MIN_DEPTH_CM = 0.0
MAX_DEPTH_CM = 300.0

VALID_METHODS = frozenset({"hassink", "six"})

REQUIRED_DF_COLUMNS = frozenset({
    "clay_pct",
    "silt_pct",
    "bulk_density_g_cm3",
    "depth_cm",
    "soc_stock_tC_ha",
})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SaturationInputs:
    """Inputs for a single-profile SOC saturation calculation.

    Attributes
    ----------
    clay_pct:
        Clay fraction (% by mass), 0-100.
    silt_pct:
        Silt fraction (% by mass), 0-100.
    bulk_density_g_cm3:
        Dry bulk density in g/cm3.
    depth_cm:
        Soil layer thickness in centimetres.
    current_soc_stock_tC_ha:
        Measured SOC stock for the same layer in tC/ha.
    method:
        "hassink" (default) or "six" — chooses the pedotransfer coefficients.
    """

    clay_pct: float
    silt_pct: float
    bulk_density_g_cm3: float
    depth_cm: float
    current_soc_stock_tC_ha: float
    method: str = "hassink"


@dataclass(frozen=True)
class SaturationResult:
    """Result of a saturation calculation.

    All stocks are in tC/ha for the specified soil layer.

    Attributes
    ----------
    c_sat_g_per_kg:
        Saturation concentration of the fine fraction, in g C per kg soil.
    c_sat_stock_tC_ha:
        Saturation stock for the layer in tC/ha.
    current_soc_stock_tC_ha:
        Measured SOC stock (echoed from the input).
    saturation_deficit_tC_ha:
        c_sat_stock - current (clipped to >= 0).
    saturation_ratio:
        current / c_sat_stock (0-1+; >1 means super-saturated).
    method:
        Pedotransfer method used.
    """

    c_sat_g_per_kg: float
    c_sat_stock_tC_ha: float
    current_soc_stock_tC_ha: float
    saturation_deficit_tC_ha: float
    saturation_ratio: float
    method: str


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def _coefficients(method: str) -> tuple[float, float]:
    """Return (intercept, slope) in g C / kg soil for *method*."""
    if method == "hassink":
        return HASSINK_INTERCEPT_G_KG, HASSINK_SLOPE_G_KG
    if method == "six":
        return SIX_INTERCEPT_G_KG, SIX_SLOPE_G_KG
    raise ValueError(
        f"Unknown method '{method}'. Expected one of: {sorted(VALID_METHODS)}"
    )


def calculate_c_saturation(
    clay_pct: float,
    silt_pct: float,
    method: str = "hassink",
) -> float:
    """Compute the SOC saturation concentration (g C / kg soil).

    Applies the Hassink 1997 (or Six 2002) linear pedotransfer function::

        C_sat = a + b * (clay_pct + silt_pct)

    Parameters
    ----------
    clay_pct:
        Clay content in % (0-100).
    silt_pct:
        Silt content in % (0-100).
    method:
        Either "hassink" (default) or "six".

    Returns
    -------
    float
        Saturation concentration in g C per kg of whole soil, rounded
        to four decimal places.

    Raises
    ------
    ValueError
        If any input is out of range or if the method is unknown.
    """
    _validate_pct("clay_pct", clay_pct)
    _validate_pct("silt_pct", silt_pct)
    if clay_pct + silt_pct > MAX_PCT:
        raise ValueError(
            f"clay_pct + silt_pct must be <= {MAX_PCT}, "
            f"got {clay_pct + silt_pct}"
        )
    intercept, slope = _coefficients(method)
    c_sat = intercept + slope * (clay_pct + silt_pct)
    return round(c_sat, 4)


def c_sat_stock_tC_ha(
    c_sat_g_per_kg: float,
    bulk_density_g_cm3: float,
    depth_cm: float,
) -> float:
    """Convert a saturation concentration to a per-hectare stock.

    Derivation:  1 g/kg * 1 g/cm3 * 1 cm over 1 ha = 0.1 tC/ha.

    Parameters
    ----------
    c_sat_g_per_kg:
        Saturation concentration (g C / kg soil).  Must be >= 0.
    bulk_density_g_cm3:
        Dry bulk density (g/cm3).
    depth_cm:
        Layer thickness (cm).

    Returns
    -------
    float
        Saturation stock in tC/ha, rounded to two decimal places.

    Raises
    ------
    ValueError
        If any parameter is out of range.
    """
    if c_sat_g_per_kg < 0:
        raise ValueError(
            f"c_sat_g_per_kg must be >= 0, got {c_sat_g_per_kg}"
        )
    _validate_bulk_density(bulk_density_g_cm3)
    _validate_depth(depth_cm)
    stock = c_sat_g_per_kg * bulk_density_g_cm3 * depth_cm * 0.1
    return round(stock, 2)


def calculate_saturation(inputs: SaturationInputs) -> SaturationResult:
    """Compute the full saturation result for a single soil layer.

    This is the high-level entry point.  It never mutates *inputs*.

    Parameters
    ----------
    inputs:
        A :class:`SaturationInputs` dataclass instance.

    Returns
    -------
    SaturationResult
        Immutable result object.

    Raises
    ------
    ValueError
        Propagated from underlying validators.
    """
    if not isinstance(inputs, SaturationInputs):
        raise TypeError(
            f"Expected SaturationInputs, got {type(inputs).__name__}"
        )
    _validate_bulk_density(inputs.bulk_density_g_cm3)
    _validate_depth(inputs.depth_cm)
    if inputs.current_soc_stock_tC_ha < 0:
        raise ValueError(
            "current_soc_stock_tC_ha must be >= 0, "
            f"got {inputs.current_soc_stock_tC_ha}"
        )

    c_sat = calculate_c_saturation(
        inputs.clay_pct, inputs.silt_pct, method=inputs.method
    )
    sat_stock = c_sat_stock_tC_ha(
        c_sat, inputs.bulk_density_g_cm3, inputs.depth_cm
    )
    deficit = max(sat_stock - inputs.current_soc_stock_tC_ha, 0.0)
    ratio = (
        inputs.current_soc_stock_tC_ha / sat_stock
        if sat_stock > 0
        else 0.0
    )
    return SaturationResult(
        c_sat_g_per_kg=c_sat,
        c_sat_stock_tC_ha=sat_stock,
        current_soc_stock_tC_ha=round(inputs.current_soc_stock_tC_ha, 2),
        saturation_deficit_tC_ha=round(deficit, 2),
        saturation_ratio=round(ratio, 4),
        method=inputs.method,
    )


def with_method(inputs: SaturationInputs, method: str) -> SaturationInputs:
    """Return a new :class:`SaturationInputs` with the method changed.

    Uses :func:`dataclasses.replace` to preserve immutability.
    """
    if method not in VALID_METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Expected one of: {sorted(VALID_METHODS)}"
        )
    return replace(inputs, method=method)


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------


def validate_saturation_dataframe(df: pd.DataFrame) -> None:
    """Check that *df* has the columns and types required for batch saturation.

    Raises
    ------
    TypeError
        If *df* is not a :class:`pandas.DataFrame`.
    ValueError
        If *df* is empty, missing columns, or has non-numeric data.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"Expected a pandas DataFrame, got {type(df).__name__}"
        )
    if df.empty:
        raise ValueError("DataFrame is empty — no rows to process")
    missing = REQUIRED_DF_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"DataFrame is missing required columns: {sorted(missing)}"
        )
    for col in REQUIRED_DF_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(
                f"Column '{col}' must be numeric, got dtype {df[col].dtype}"
            )


def add_saturation_columns(
    df: pd.DataFrame,
    method: str = "hassink",
) -> pd.DataFrame:
    """Return a new DataFrame with saturation metrics appended.

    The following columns are added (the original *df* is never mutated):

    * ``c_sat_g_per_kg``
    * ``c_sat_stock_tC_ha``
    * ``saturation_deficit_tC_ha``
    * ``saturation_ratio``

    Rows with missing or out-of-range values yield ``NaN`` in all four
    new columns and are never raised on.

    Parameters
    ----------
    df:
        Input DataFrame with the required columns.
    method:
        Pedotransfer method — "hassink" (default) or "six".

    Returns
    -------
    pd.DataFrame
        A copy of *df* with four new columns.

    Raises
    ------
    ValueError
        Propagated from :func:`validate_saturation_dataframe`, or if
        *method* is not recognised.
    """
    if method not in VALID_METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Expected one of: {sorted(VALID_METHODS)}"
        )
    validate_saturation_dataframe(df)
    result = df.copy()

    def _row_result(row: pd.Series) -> tuple[float, float, float, float]:
        try:
            inputs = SaturationInputs(
                clay_pct=float(row["clay_pct"]),
                silt_pct=float(row["silt_pct"]),
                bulk_density_g_cm3=float(row["bulk_density_g_cm3"]),
                depth_cm=float(row["depth_cm"]),
                current_soc_stock_tC_ha=float(row["soc_stock_tC_ha"]),
                method=method,
            )
            res = calculate_saturation(inputs)
            return (
                res.c_sat_g_per_kg,
                res.c_sat_stock_tC_ha,
                res.saturation_deficit_tC_ha,
                res.saturation_ratio,
            )
        except (ValueError, TypeError):
            return (np.nan, np.nan, np.nan, np.nan)

    applied = result.apply(_row_result, axis=1, result_type="expand")
    applied.columns = [
        "c_sat_g_per_kg",
        "c_sat_stock_tC_ha",
        "saturation_deficit_tC_ha",
        "saturation_ratio",
    ]
    for col in applied.columns:
        result[col] = applied[col]
    return result


def summarise_saturation(df: pd.DataFrame) -> dict[str, Optional[float]]:
    """Return summary statistics for a DataFrame that already has saturation columns.

    Parameters
    ----------
    df:
        DataFrame expected to contain ``saturation_deficit_tC_ha`` and
        ``saturation_ratio`` columns (e.g., from :func:`add_saturation_columns`).

    Returns
    -------
    dict
        Keys: ``mean_deficit_tC_ha``, ``total_deficit_tC_ha``,
        ``mean_ratio``, ``n_saturated`` (ratio >= 1.0), ``n_valid``.

    Raises
    ------
    ValueError
        If expected columns are missing.
    """
    for col in ("saturation_deficit_tC_ha", "saturation_ratio"):
        if col not in df.columns:
            raise ValueError(f"DataFrame is missing column '{col}'")
    valid = df.dropna(subset=["saturation_deficit_tC_ha", "saturation_ratio"])
    if valid.empty:
        return {
            "mean_deficit_tC_ha": None,
            "total_deficit_tC_ha": None,
            "mean_ratio": None,
            "n_saturated": 0,
            "n_valid": 0,
        }
    return {
        "mean_deficit_tC_ha": round(float(valid["saturation_deficit_tC_ha"].mean()), 2),
        "total_deficit_tC_ha": round(float(valid["saturation_deficit_tC_ha"].sum()), 2),
        "mean_ratio": round(float(valid["saturation_ratio"].mean()), 4),
        "n_saturated": int((valid["saturation_ratio"] >= 1.0).sum()),
        "n_valid": int(len(valid)),
    }


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _validate_pct(name: str, value: float) -> None:
    if value < MIN_PCT:
        raise ValueError(f"{name} must be >= {MIN_PCT}, got {value}")
    if value > MAX_PCT:
        raise ValueError(f"{name} must be <= {MAX_PCT}, got {value}")


def _validate_bulk_density(value: float) -> None:
    if value < MIN_BULK_DENSITY:
        raise ValueError(
            f"bulk_density_g_cm3 must be >= {MIN_BULK_DENSITY}, got {value}"
        )
    if value > MAX_BULK_DENSITY:
        raise ValueError(
            f"bulk_density_g_cm3 {value} exceeds physical maximum "
            f"of {MAX_BULK_DENSITY} g/cm3"
        )


def _validate_depth(value: float) -> None:
    if value <= MIN_DEPTH_CM:
        raise ValueError(f"depth_cm must be > {MIN_DEPTH_CM}, got {value}")
    if value > MAX_DEPTH_CM:
        raise ValueError(
            f"depth_cm {value} exceeds maximum supported depth "
            f"of {MAX_DEPTH_CM} cm"
        )
