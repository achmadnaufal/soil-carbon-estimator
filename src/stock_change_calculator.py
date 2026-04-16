"""
SOC stock change calculator for paired soil survey datasets.

Computes the change in soil organic carbon (SOC) stock between two survey
periods, the annualised accrual rate, and 95 % confidence-interval uncertainty
bands propagated from per-site measurement error.

The module follows immutable data patterns: every public function returns a
new DataFrame or dataclass and never mutates its inputs.

Typical workflow::

    from src.stock_change_calculator import compute_stock_change

    result_df = compute_stock_change(
        survey_t0=df_2020,
        survey_t1=df_2024,
        years_elapsed=4.0,
        site_id_col="site_id",
    )

Author: github.com/achmadnaufal
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SITE_ID_COL = "site_id"
_SOC_COL = "soc_stock_tC_ha"
# Assumed relative measurement uncertainty (coefficient of variation) when
# per-site error information is not provided in the input data.
_DEFAULT_CV = 0.05  # 5 % relative uncertainty — conservative field estimate
_Z_95 = 1.96        # z-score for 95 % two-sided confidence interval


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockChangeSummary:
    """Aggregate summary of SOC stock change across all matched sites.

    Attributes:
        n_sites: Number of matched sites included in the analysis.
        mean_delta_tC_ha: Mean per-site SOC stock change (tC/ha).
        total_delta_tC_ha: Sum of per-site SOC stock changes (tC/ha).
        mean_annual_rate_tC_ha_yr: Mean annualised accrual rate (tC/ha/yr).
        ci_lower_tC_ha: Lower bound of the 95 % CI on mean_delta_tC_ha.
        ci_upper_tC_ha: Upper bound of the 95 % CI on mean_delta_tC_ha.
        years_elapsed: Survey interval used for annualisation (years).
    """

    n_sites: int
    mean_delta_tC_ha: float
    total_delta_tC_ha: float
    mean_annual_rate_tC_ha_yr: float
    ci_lower_tC_ha: float
    ci_upper_tC_ha: float
    years_elapsed: float


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require_dataframe(obj: object, name: str) -> None:
    """Raise TypeError when *obj* is not a pandas DataFrame.

    Args:
        obj: Object to check.
        name: Parameter name for the error message.

    Raises:
        TypeError: If *obj* is not a :class:`pandas.DataFrame`.
    """
    if not isinstance(obj, pd.DataFrame):
        raise TypeError(
            f"'{name}' must be a pandas DataFrame, got {type(obj).__name__}"
        )


def _require_soc_column(df: pd.DataFrame, name: str) -> None:
    """Raise ValueError when *df* lacks the ``soc_stock_tC_ha`` column.

    Args:
        df: DataFrame to inspect.
        name: Parameter name for the error message.

    Raises:
        ValueError: If the required SOC stock column is absent.
    """
    if _SOC_COL not in df.columns:
        raise ValueError(
            f"'{name}' must contain a '{_SOC_COL}' column. "
            f"Available columns: {list(df.columns)}"
        )


def _validate_years_elapsed(years_elapsed: float) -> None:
    """Raise ValueError for non-positive or non-finite *years_elapsed*.

    Args:
        years_elapsed: Survey interval in years.

    Raises:
        ValueError: If *years_elapsed* is <= 0 or not finite.
    """
    if not np.isfinite(years_elapsed):
        raise ValueError(
            f"'years_elapsed' must be a finite number, got {years_elapsed}"
        )
    if years_elapsed <= 0:
        raise ValueError(
            f"'years_elapsed' must be > 0 to compute an annualised rate, "
            f"got {years_elapsed}"
        )


# ---------------------------------------------------------------------------
# Core public functions
# ---------------------------------------------------------------------------


def compute_stock_change(
    survey_t0: pd.DataFrame,
    survey_t1: pd.DataFrame,
    years_elapsed: float,
    site_id_col: str = _DEFAULT_SITE_ID_COL,
    error_col: Optional[str] = None,
) -> pd.DataFrame:
    """Compute per-site SOC stock change between two survey DataFrames.

    Both DataFrames must contain a ``soc_stock_tC_ha`` column and a common
    site-identifier column.  Only sites present in *both* surveys are
    included in the output (inner join on *site_id_col*).

    The function never mutates *survey_t0* or *survey_t1*.

    Args:
        survey_t0: DataFrame from the earlier survey (time-zero).  Must
            contain *site_id_col* and ``soc_stock_tC_ha``.
        survey_t1: DataFrame from the later survey (time-one).  Same
            requirements as *survey_t0*.
        years_elapsed: Number of years between the two surveys.  Must be
            strictly positive.
        site_id_col: Name of the column that uniquely identifies each
            sampling site.  Defaults to ``"site_id"``.
        error_col: Optional column name holding per-site absolute
            uncertainty (tC/ha, 1-sigma) in *both* DataFrames.  When
            ``None``, a default relative uncertainty of 5 % is applied.

    Returns:
        A new DataFrame with one row per matched site containing:

        * *site_id_col* — site identifier
        * ``soc_t0_tC_ha`` — SOC stock at time-zero (tC/ha)
        * ``soc_t1_tC_ha`` — SOC stock at time-one (tC/ha)
        * ``delta_soc_tC_ha`` — absolute change (t1 − t0, tC/ha)
        * ``annual_rate_tC_ha_yr`` — annualised accrual rate (tC/ha/yr)
        * ``ci_lower_tC_ha`` — lower 95 % CI bound on delta (tC/ha)
        * ``ci_upper_tC_ha`` — upper 95 % CI bound on delta (tC/ha)

    Raises:
        TypeError: If either survey argument is not a DataFrame.
        ValueError: If required columns are missing, *years_elapsed* is
            invalid, or no matching sites are found.

    Example:
        >>> import pandas as pd
        >>> from src.stock_change_calculator import compute_stock_change
        >>> t0 = pd.DataFrame({
        ...     "site_id": ["A", "B"],
        ...     "soc_stock_tC_ha": [80.0, 60.0],
        ... })
        >>> t1 = pd.DataFrame({
        ...     "site_id": ["A", "B"],
        ...     "soc_stock_tC_ha": [88.0, 66.0],
        ... })
        >>> result = compute_stock_change(t0, t1, years_elapsed=4.0)
        >>> list(result["delta_soc_tC_ha"])
        [8.0, 6.0]
        >>> list(result["annual_rate_tC_ha_yr"])
        [2.0, 1.5]
    """
    _require_dataframe(survey_t0, "survey_t0")
    _require_dataframe(survey_t1, "survey_t1")
    _validate_years_elapsed(years_elapsed)

    if site_id_col not in survey_t0.columns:
        raise ValueError(
            f"site_id_col '{site_id_col}' not found in survey_t0. "
            f"Available: {list(survey_t0.columns)}"
        )
    if site_id_col not in survey_t1.columns:
        raise ValueError(
            f"site_id_col '{site_id_col}' not found in survey_t1. "
            f"Available: {list(survey_t1.columns)}"
        )

    _require_soc_column(survey_t0, "survey_t0")
    _require_soc_column(survey_t1, "survey_t1")

    # Select only the columns we need — avoids column name clashes on merge
    cols_t0 = [site_id_col, _SOC_COL]
    cols_t1 = [site_id_col, _SOC_COL]
    if error_col is not None:
        if error_col not in survey_t0.columns:
            raise ValueError(
                f"error_col '{error_col}' not found in survey_t0"
            )
        if error_col not in survey_t1.columns:
            raise ValueError(
                f"error_col '{error_col}' not found in survey_t1"
            )
        cols_t0 = cols_t0 + [error_col]
        cols_t1 = cols_t1 + [error_col]

    left = survey_t0[cols_t0].copy()
    right = survey_t1[cols_t1].copy()

    merged = left.merge(
        right,
        on=site_id_col,
        how="inner",
        suffixes=("_t0", "_t1"),
    )

    if merged.empty:
        raise ValueError(
            "No matching sites found between survey_t0 and survey_t1 "
            f"on column '{site_id_col}'. Check that site identifiers overlap."
        )

    soc_t0 = merged[f"{_SOC_COL}_t0"]
    soc_t1 = merged[f"{_SOC_COL}_t1"]
    delta = soc_t1 - soc_t0

    # Propagate uncertainty: sigma_delta = sqrt(sigma_t0^2 + sigma_t1^2)
    if error_col is not None:
        sigma_t0 = merged[f"{error_col}_t0"]
        sigma_t1 = merged[f"{error_col}_t1"]
    else:
        sigma_t0 = soc_t0.abs() * _DEFAULT_CV
        sigma_t1 = soc_t1.abs() * _DEFAULT_CV

    sigma_delta = np.sqrt(sigma_t0**2 + sigma_t1**2)
    half_width = _Z_95 * sigma_delta

    result = pd.DataFrame(
        {
            site_id_col: merged[site_id_col].values,
            "soc_t0_tC_ha": soc_t0.round(4).values,
            "soc_t1_tC_ha": soc_t1.round(4).values,
            "delta_soc_tC_ha": delta.round(4).values,
            "annual_rate_tC_ha_yr": (delta / years_elapsed).round(4).values,
            "ci_lower_tC_ha": (delta - half_width).round(4).values,
            "ci_upper_tC_ha": (delta + half_width).round(4).values,
        }
    )
    return result


def summarise_stock_change(
    change_df: pd.DataFrame,
    years_elapsed: float,
) -> StockChangeSummary:
    """Aggregate per-site stock-change results into a summary dataclass.

    Args:
        change_df: Output of :func:`compute_stock_change`.  Must contain
            ``delta_soc_tC_ha`` and ``annual_rate_tC_ha_yr`` columns.
        years_elapsed: Survey interval in years (used to record provenance
            in the returned dataclass).

    Returns:
        A frozen :class:`StockChangeSummary` dataclass with aggregate
        statistics rounded to four decimal places.

    Raises:
        TypeError: If *change_df* is not a DataFrame.
        ValueError: If required columns are missing or the DataFrame is
            empty.

    Example:
        >>> import pandas as pd
        >>> from src.stock_change_calculator import (
        ...     compute_stock_change, summarise_stock_change
        ... )
        >>> t0 = pd.DataFrame({
        ...     "site_id": ["A", "B"],
        ...     "soc_stock_tC_ha": [80.0, 60.0],
        ... })
        >>> t1 = pd.DataFrame({
        ...     "site_id": ["A", "B"],
        ...     "soc_stock_tC_ha": [88.0, 66.0],
        ... })
        >>> result = compute_stock_change(t0, t1, years_elapsed=4.0)
        >>> summary = summarise_stock_change(result, years_elapsed=4.0)
        >>> summary.n_sites
        2
        >>> summary.mean_delta_tC_ha
        7.0
    """
    _require_dataframe(change_df, "change_df")
    _validate_years_elapsed(years_elapsed)

    required = {"delta_soc_tC_ha", "annual_rate_tC_ha_yr"}
    missing = required - set(change_df.columns)
    if missing:
        raise ValueError(
            f"change_df is missing required columns: {sorted(missing)}"
        )
    if change_df.empty:
        raise ValueError("change_df is empty — no rows to summarise")

    deltas = change_df["delta_soc_tC_ha"].dropna()
    if deltas.empty:
        raise ValueError(
            "All 'delta_soc_tC_ha' values are NaN — nothing to summarise"
        )

    n = len(deltas)
    mean_delta = float(deltas.mean())
    total_delta = float(deltas.sum())
    mean_rate = float(change_df["annual_rate_tC_ha_yr"].dropna().mean())

    # 95 % CI on the mean delta using standard error of the mean
    if n > 1:
        se = float(deltas.std(ddof=1) / np.sqrt(n))
        half_width = _Z_95 * se
    else:
        half_width = 0.0

    return StockChangeSummary(
        n_sites=n,
        mean_delta_tC_ha=round(mean_delta, 4),
        total_delta_tC_ha=round(total_delta, 4),
        mean_annual_rate_tC_ha_yr=round(mean_rate, 4),
        ci_lower_tC_ha=round(mean_delta - half_width, 4),
        ci_upper_tC_ha=round(mean_delta + half_width, 4),
        years_elapsed=years_elapsed,
    )
