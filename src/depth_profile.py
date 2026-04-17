"""
Depth-profile interpolation utilities for soil organic carbon (SOC) data.

Most field campaigns sample SOC at site-specific, irregular depth horizons
(e.g. 0-10, 10-20, 20-40 cm), but downstream reporting (IPCC, FAO GSOC,
Verra VM0042) typically requires SOC stock harmonised to a *reference*
depth such as 0-30 cm or 0-100 cm.  This module provides:

* :func:`interpolate_soc_profile` - Resample an irregular SOC depth profile
  onto a regular depth grid using monotone-preserving interpolation.
* :func:`integrate_soc_to_depth` - Integrate a measured profile to a target
  reference depth, returning the cumulative SOC stock (tC/ha) using either
  trapezoidal numeric integration or an exponential-decay fit
  (Hilinski / Bernoux model) for extrapolation beyond the deepest sample.
* :func:`harmonise_to_reference_depth` - Convenience wrapper that applies
  :func:`integrate_soc_to_depth` per site to a long-format DataFrame and
  returns one row per site at the target reference depth.

All public functions follow immutable patterns - they return new objects
and never mutate their inputs.

Example:
    >>> import pandas as pd
    >>> from src.depth_profile import integrate_soc_to_depth
    >>> depths = [10.0, 20.0, 40.0]
    >>> stocks = [25.0, 22.0, 18.0]   # tC/ha per horizon
    >>> total_30cm = integrate_soc_to_depth(depths, stocks, target_depth_cm=30)
    >>> round(total_30cm, 2)
    56.0

Author: github.com/achmadnaufal
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SITE_ID_COL = "site_id"
_DEPTH_COL = "depth_cm"
_SOC_COL = "soc_stock_tC_ha"
_MAX_DEPTH_CM = 300.0  # consistent with src.soc_calculator.MAX_DEPTH_CM
# Default exponential decay constant (1/cm) used when extrapolating beyond
# the deepest measured horizon and only one data point is available.  Value
# from Bernoux et al. (1998) for tropical soils, k ~= 0.025.
_DEFAULT_DECAY_K = 0.025


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _validate_profile(
    depths_cm: Sequence[float],
    stocks: Sequence[float],
) -> Tuple[np.ndarray, np.ndarray]:
    """Coerce and validate a depth/stock profile to sorted NumPy arrays.

    Args:
        depths_cm: Iterable of horizon depths in centimetres.  Each entry
            represents the *lower* boundary of a sampled horizon.
        stocks: Iterable of per-horizon SOC stock values (tC/ha) aligned
            element-wise with *depths_cm*.

    Returns:
        Tuple ``(depths, stocks)`` of NumPy arrays sorted by ascending depth.

    Raises:
        TypeError: If either argument is not iterable or contains
            non-numeric values.
        ValueError: If lengths differ, the profile is empty, depths or
            stocks contain NaN/negative values, depths exceed the supported
            maximum, or duplicate depth entries are present.
    """
    if isinstance(depths_cm, (str, bytes)) or isinstance(stocks, (str, bytes)):
        raise TypeError("'depths_cm' and 'stocks' must be numeric sequences")

    try:
        depth_arr = np.asarray(list(depths_cm), dtype=float)
        stock_arr = np.asarray(list(stocks), dtype=float)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"'depths_cm' and 'stocks' must contain numeric values: {exc}"
        ) from exc

    if depth_arr.size == 0:
        raise ValueError("Profile is empty - depths_cm and stocks are required")
    if depth_arr.size != stock_arr.size:
        raise ValueError(
            f"Length mismatch: depths_cm has {depth_arr.size} entries, "
            f"stocks has {stock_arr.size}"
        )
    if np.isnan(depth_arr).any() or np.isnan(stock_arr).any():
        raise ValueError("Profile contains NaN values - clean inputs first")
    if (depth_arr <= 0).any():
        raise ValueError(
            f"All depths_cm must be > 0, got {depth_arr.tolist()}"
        )
    if (depth_arr > _MAX_DEPTH_CM).any():
        raise ValueError(
            f"depths_cm contains values > {_MAX_DEPTH_CM} cm "
            f"(physical maximum): {depth_arr.tolist()}"
        )
    if (stock_arr < 0).any():
        raise ValueError(
            f"SOC stocks must be >= 0, got {stock_arr.tolist()}"
        )

    order = np.argsort(depth_arr)
    depth_sorted = depth_arr[order]
    stock_sorted = stock_arr[order]

    if np.any(np.diff(depth_sorted) == 0):
        raise ValueError(
            f"Duplicate depth entries are not allowed: {depth_sorted.tolist()}"
        )

    return depth_sorted, stock_sorted


def _validate_target_depth(target_depth_cm: float) -> float:
    """Validate and return a target reference depth (cm).

    Args:
        target_depth_cm: Depth at which to evaluate the profile.

    Returns:
        Validated target depth as a float.

    Raises:
        TypeError: If *target_depth_cm* is not numeric.
        ValueError: If <= 0 or > :data:`_MAX_DEPTH_CM`.
    """
    try:
        value = float(target_depth_cm)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"'target_depth_cm' must be numeric, got {type(target_depth_cm).__name__}"
        ) from exc
    if not np.isfinite(value):
        raise ValueError(f"'target_depth_cm' must be finite, got {value}")
    if value <= 0:
        raise ValueError(f"'target_depth_cm' must be > 0, got {value}")
    if value > _MAX_DEPTH_CM:
        raise ValueError(
            f"'target_depth_cm' {value} exceeds physical maximum {_MAX_DEPTH_CM} cm"
        )
    return value


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def interpolate_soc_profile(
    depths_cm: Sequence[float],
    stocks: Sequence[float],
    target_depths_cm: Sequence[float],
) -> List[float]:
    """Interpolate per-horizon SOC stocks onto a regular depth grid.

    Uses linear interpolation between measured horizons.  Target depths
    that fall *above* the shallowest sample are clamped to the shallowest
    measured value; target depths *below* the deepest sample are clamped
    to the deepest value (no extrapolation - use
    :func:`integrate_soc_to_depth` for extrapolation).

    Args:
        depths_cm: Sequence of horizon depths in centimetres (must be
            positive, non-duplicated).
        stocks: Per-horizon SOC stocks in tC/ha aligned with *depths_cm*.
        target_depths_cm: Depths at which to evaluate the interpolated
            stock.  May be unsorted; output preserves the input order.

    Returns:
        List of interpolated SOC stock values (tC/ha), one per entry in
        *target_depths_cm*.

    Raises:
        TypeError: If any argument is not a numeric sequence.
        ValueError: If inputs are empty, lengths mismatch, or contain
            invalid values (NaN, negative depths, > 300 cm).

    Example:
        >>> interpolate_soc_profile([10, 20, 40], [25.0, 22.0, 18.0], [15, 30])
        [23.5, 20.0]
    """
    depth_arr, stock_arr = _validate_profile(depths_cm, stocks)

    try:
        target_arr = np.asarray(list(target_depths_cm), dtype=float)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"'target_depths_cm' must contain numeric values: {exc}"
        ) from exc
    if target_arr.size == 0:
        raise ValueError("'target_depths_cm' is empty")
    if np.isnan(target_arr).any():
        raise ValueError("'target_depths_cm' contains NaN")
    if (target_arr <= 0).any():
        raise ValueError(
            f"All 'target_depths_cm' must be > 0, got {target_arr.tolist()}"
        )

    interpolated = np.interp(target_arr, depth_arr, stock_arr)
    return [round(float(v), 4) for v in interpolated]


def integrate_soc_to_depth(
    depths_cm: Sequence[float],
    stocks: Sequence[float],
    target_depth_cm: float,
    extrapolate: bool = True,
) -> float:
    """Integrate a SOC profile to a target reference depth (tC/ha).

    The measured profile is treated as the SOC stock per horizon
    (tC/ha contained in the layer ending at the given depth).  For a
    target depth that lies *between* sampled horizons, the contribution
    of the partial horizon is estimated via linear interpolation of the
    cumulative stock curve.

    For target depths *beyond* the deepest sample, two strategies apply:

    * ``extrapolate=True`` (default): an exponential decay model
      ``stock(d) = a * exp(-k * d)`` is fitted (or, with a single sample,
      the literature-default ``k = 0.025`` is used) and integrated
      analytically out to *target_depth_cm*.
    * ``extrapolate=False``: the profile is truncated at the deepest
      sample and a :class:`ValueError` is raised.

    Args:
        depths_cm: Per-horizon lower-boundary depths (cm), strictly > 0.
        stocks: Per-horizon SOC stocks (tC/ha), aligned with *depths_cm*.
        target_depth_cm: Reference depth at which to evaluate the
            cumulative stock.  Must be > 0 and <= 300 cm.
        extrapolate: If ``True`` and *target_depth_cm* exceeds the deepest
            measured horizon, fit an exponential-decay model to extrapolate.

    Returns:
        Cumulative SOC stock from surface to *target_depth_cm*, in tC/ha,
        rounded to four decimal places.

    Raises:
        TypeError: If inputs are not numeric sequences / scalar.
        ValueError: If profile is invalid, *target_depth_cm* is out of range,
            or extrapolation is requested but disabled.

    Example:
        >>> # Three horizons covering 0-40 cm, harmonised to 0-30 cm
        >>> integrate_soc_to_depth([10, 20, 40], [25.0, 22.0, 18.0], 30)
        56.0
    """
    depth_arr, stock_arr = _validate_profile(depths_cm, stocks)
    target = _validate_target_depth(target_depth_cm)

    deepest = float(depth_arr[-1])

    # Cumulative stock at each measured boundary
    cumulative = np.cumsum(stock_arr)

    if target <= deepest:
        # Linear interpolation of the cumulative-stock curve.  Anchor the
        # curve at depth=0, stock=0 so shallow targets behave correctly.
        anchor_depth = np.concatenate(([0.0], depth_arr))
        anchor_cum = np.concatenate(([0.0], cumulative))
        result = float(np.interp(target, anchor_depth, anchor_cum))
        return round(result, 4)

    # target > deepest measured horizon
    if not extrapolate:
        raise ValueError(
            f"target_depth_cm {target} exceeds deepest measured depth "
            f"{deepest} and extrapolate=False"
        )

    base_cumulative = float(cumulative[-1])
    extra = _exponential_extrapolate(
        depth_arr=depth_arr,
        stock_arr=stock_arr,
        from_depth_cm=deepest,
        to_depth_cm=target,
    )
    return round(base_cumulative + extra, 4)


def harmonise_to_reference_depth(
    df: pd.DataFrame,
    target_depth_cm: float,
    site_id_col: str = _DEFAULT_SITE_ID_COL,
    depth_col: str = _DEPTH_COL,
    stock_col: str = _SOC_COL,
    extrapolate: bool = True,
) -> pd.DataFrame:
    """Harmonise per-horizon SOC stocks to a single reference depth, per site.

    Long-format soil-survey DataFrames typically contain one row per
    (site, horizon).  This function groups by *site_id_col* and applies
    :func:`integrate_soc_to_depth` to each site's profile, returning one
    row per site with the harmonised cumulative stock.

    Args:
        df: Long-format DataFrame with at least the columns
            *site_id_col*, *depth_col*, and *stock_col*.
        target_depth_cm: Reference depth (cm) to harmonise every site to.
        site_id_col: Column identifying each sampling site.
        depth_col: Column with horizon lower-boundary depths (cm).
        stock_col: Column with per-horizon SOC stocks (tC/ha).
        extrapolate: Forwarded to :func:`integrate_soc_to_depth`.

    Returns:
        New DataFrame with columns ``[site_id_col, "soc_stock_tC_ha",
        "reference_depth_cm", "n_horizons"]`` - one row per site.

    Raises:
        TypeError: If *df* is not a :class:`pandas.DataFrame`.
        ValueError: If required columns are missing or the DataFrame is
            empty.

    Example:
        >>> import pandas as pd
        >>> from src.depth_profile import harmonise_to_reference_depth
        >>> df = pd.DataFrame({
        ...     "site_id": ["A", "A", "B", "B"],
        ...     "depth_cm": [10, 30, 10, 30],
        ...     "soc_stock_tC_ha": [25.0, 22.0, 30.0, 28.0],
        ... })
        >>> out = harmonise_to_reference_depth(df, target_depth_cm=30)
        >>> sorted(out.columns.tolist())
        ['n_horizons', 'reference_depth_cm', 'site_id', 'soc_stock_tC_ha']
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"'df' must be a pandas DataFrame, got {type(df).__name__}"
        )
    target = _validate_target_depth(target_depth_cm)

    missing = {site_id_col, depth_col, stock_col} - set(df.columns)
    if missing:
        raise ValueError(
            f"DataFrame is missing required columns: {sorted(missing)}. "
            f"Available: {list(df.columns)}"
        )
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    rows = []
    for site_id, group in df.groupby(site_id_col, sort=True):
        depths = group[depth_col].tolist()
        stocks = group[stock_col].tolist()
        cumulative = integrate_soc_to_depth(
            depths_cm=depths,
            stocks=stocks,
            target_depth_cm=target,
            extrapolate=extrapolate,
        )
        rows.append(
            {
                site_id_col: site_id,
                "soc_stock_tC_ha": cumulative,
                "reference_depth_cm": target,
                "n_horizons": len(group),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Private extrapolation helpers
# ---------------------------------------------------------------------------


def _exponential_extrapolate(
    depth_arr: np.ndarray,
    stock_arr: np.ndarray,
    from_depth_cm: float,
    to_depth_cm: float,
) -> float:
    """Estimate additional SOC stock between two depths via exponential decay.

    Fits ``stock_density(d) = a * exp(-k * d)`` to the per-horizon stock
    densities (tC/ha/cm) of the measured profile and integrates the fit
    from *from_depth_cm* to *to_depth_cm*.  When fewer than two horizons
    are available - or the fit produces a non-positive ``k`` - the
    literature-default decay rate :data:`_DEFAULT_DECAY_K` is used and
    anchored to the deepest measured stock density.

    Args:
        depth_arr: Sorted horizon depths (cm).
        stock_arr: Per-horizon SOC stocks (tC/ha) aligned with *depth_arr*.
        from_depth_cm: Lower integration bound (cm); typically the deepest
            measured horizon.
        to_depth_cm: Upper integration bound (cm); always >= from_depth_cm.

    Returns:
        Additional cumulative SOC stock (tC/ha) attributable to the layer
        between *from_depth_cm* and *to_depth_cm*.
    """
    if to_depth_cm <= from_depth_cm:
        return 0.0

    # Convert per-horizon stocks (tC/ha) into per-cm density (tC/ha/cm)
    horizon_thickness = np.diff(np.concatenate(([0.0], depth_arr)))
    density = stock_arr / horizon_thickness  # tC/ha per cm of horizon

    # Anchor density to the *midpoint* of each horizon for the decay fit
    midpoints = depth_arr - (horizon_thickness / 2.0)

    a, k = _fit_exponential(midpoints, density)

    # Analytical integral of a * exp(-k * d) from d1 to d2
    if k <= 0 or not np.isfinite(k) or not np.isfinite(a):
        # Degenerate fit -> fall back to constant extrapolation using the
        # density of the deepest horizon
        deepest_density = float(density[-1])
        return deepest_density * (to_depth_cm - from_depth_cm)

    integral = (a / k) * (np.exp(-k * from_depth_cm) - np.exp(-k * to_depth_cm))
    return float(max(integral, 0.0))


def _fit_exponential(
    depths: np.ndarray,
    densities: np.ndarray,
) -> Tuple[float, float]:
    """Fit ``density(d) = a * exp(-k * d)`` via log-linear regression.

    Args:
        depths: Depth values (cm).
        densities: Stock densities (tC/ha per cm of horizon).

    Returns:
        Tuple ``(a, k)`` of the fitted parameters.  When fitting is not
        possible (single point, non-positive density), falls back to
        anchoring at the deepest sample with :data:`_DEFAULT_DECAY_K`.
    """
    positive = densities > 0
    n_positive = int(positive.sum())

    if n_positive < 2:
        # Single usable point - anchor exponential at the deepest sample
        idx = int(np.argmax(depths))
        d_anchor = float(depths[idx])
        rho_anchor = float(densities[idx]) if densities[idx] > 0 else 0.0
        k = _DEFAULT_DECAY_K
        a = rho_anchor * np.exp(k * d_anchor)
        return a, k

    log_density = np.log(densities[positive])
    d_pos = depths[positive]

    # slope = -k, intercept = log(a)
    slope, intercept = np.polyfit(d_pos, log_density, deg=1)
    return float(np.exp(intercept)), float(-slope)
