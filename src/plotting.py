"""
Plotting utilities for soil organic carbon (SOC) stocks.

Provides pure helper functions that take DataFrames and return
matplotlib ``Figure`` objects.  Figures are never written to disk by
these helpers - callers decide when/where to persist via
:meth:`Figure.savefig`.

matplotlib is imported lazily so the rest of the package remains
usable when matplotlib is not installed.  Every helper includes a
clear ``ImportError`` message when the optional dependency is missing.

Author: github.com/achmadnaufal
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Tuple

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - only needed for static typing
    from matplotlib.figure import Figure


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SOC_COL = "soc_stock_tC_ha"
_LAND_USE_COL = "land_use"
_DEPTH_COL = "depth_cm"
_DEFAULT_FIGSIZE: Tuple[float, float] = (8.0, 5.0)
_MIN_BINS = 5
_MAX_BINS = 40


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _import_matplotlib():
    """Import :mod:`matplotlib.pyplot` with a user-friendly error.

    Returns
    -------
    module
        The ``matplotlib.pyplot`` module.

    Raises
    ------
    ImportError
        When matplotlib is not installed, with an install hint.
    """
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)  # non-interactive; safe in CI
        import matplotlib.pyplot as plt

        return plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for plotting helpers. "
            "Install it via `pip install matplotlib`."
        ) from exc


def _require_column(df: pd.DataFrame, column: str) -> None:
    """Raise ValueError if *df* is missing *column*.

    Parameters
    ----------
    df:
        DataFrame to inspect.
    column:
        Name of the required column.
    """
    if column not in df.columns:
        raise ValueError(
            f"Required column '{column}' not found in DataFrame "
            f"(available: {sorted(df.columns)})"
        )


def _require_non_empty(df: pd.DataFrame) -> None:
    """Raise ValueError when *df* is empty (zero rows).

    Parameters
    ----------
    df:
        DataFrame to inspect.
    """
    if df.empty:
        raise ValueError("Cannot plot: DataFrame is empty")


def _choose_bin_count(n: int) -> int:
    """Return a sensible bin count for a histogram with *n* observations.

    Uses the Freedman-Diaconis-inspired simple rule:
    ``max(MIN_BINS, min(MAX_BINS, round(sqrt(n))))``.

    Parameters
    ----------
    n:
        Sample size.

    Returns
    -------
    int
        Bin count, clamped to [_MIN_BINS, _MAX_BINS].
    """
    if n <= 0:
        return _MIN_BINS
    bins = int(round(np.sqrt(max(n, 1))))
    return max(_MIN_BINS, min(_MAX_BINS, bins))


# ---------------------------------------------------------------------------
# Public plotting functions
# ---------------------------------------------------------------------------


def plot_soc_histogram(
    df: pd.DataFrame,
    column: str = _SOC_COL,
    bins: Optional[int] = None,
    title: Optional[str] = None,
    figsize: Tuple[float, float] = _DEFAULT_FIGSIZE,
) -> "Figure":
    """Plot a histogram of SOC stock values.

    The input DataFrame is never mutated.  ``NaN`` values are dropped
    prior to binning.

    Parameters
    ----------
    df:
        Input DataFrame containing at least *column*.
    column:
        Numeric column to histogram.  Defaults to ``"soc_stock_tC_ha"``.
    bins:
        Number of histogram bins.  When ``None`` the bin count is chosen
        automatically from the sample size.
    title:
        Optional plot title.  Defaults to a description of *column*.
    figsize:
        Figure size in inches, forwarded to matplotlib.

    Returns
    -------
    matplotlib.figure.Figure
        The newly-created Figure.

    Raises
    ------
    ImportError
        If matplotlib is not installed.
    ValueError
        If *df* is empty, missing *column*, or *column* contains only
        ``NaN`` values.
    """
    _require_non_empty(df)
    _require_column(df, column)

    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if values.empty:
        raise ValueError(
            f"Column '{column}' has no finite numeric values to plot"
        )

    plt = _import_matplotlib()
    bin_count = bins if bins is not None else _choose_bin_count(len(values))

    fig, ax = plt.subplots(figsize=figsize)
    ax.hist(values, bins=bin_count, edgecolor="black", alpha=0.85)
    ax.set_xlabel(f"{column} (tC/ha)")
    ax.set_ylabel("Frequency")
    ax.set_title(title or f"Distribution of {column}")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig


def plot_soc_by_land_use(
    df: pd.DataFrame,
    column: str = _SOC_COL,
    land_use_col: str = _LAND_USE_COL,
    title: Optional[str] = None,
    figsize: Tuple[float, float] = _DEFAULT_FIGSIZE,
) -> "Figure":
    """Plot a boxplot of SOC stock broken down by land-use category.

    Parameters
    ----------
    df:
        Input DataFrame containing *column* and *land_use_col*.
    column:
        Numeric column with SOC stock values (tC/ha).
    land_use_col:
        Categorical column with land-use labels.
    title:
        Optional plot title.
    figsize:
        Figure size in inches.

    Returns
    -------
    matplotlib.figure.Figure
        The newly-created Figure.

    Raises
    ------
    ImportError
        If matplotlib is not installed.
    ValueError
        If required columns are missing, the DataFrame is empty, or no
        land-use group has any finite numeric data.
    """
    _require_non_empty(df)
    _require_column(df, column)
    _require_column(df, land_use_col)

    working = df[[column, land_use_col]].copy()
    working[column] = pd.to_numeric(working[column], errors="coerce")
    working = working.dropna(subset=[column, land_use_col])
    if working.empty:
        raise ValueError(
            "No rows remain after dropping NaN in "
            f"'{column}' and '{land_use_col}'"
        )

    groups = working.groupby(land_use_col)[column]
    labels = sorted(groups.groups.keys())
    data = [groups.get_group(label).to_numpy() for label in labels]

    plt = _import_matplotlib()
    fig, ax = plt.subplots(figsize=figsize)
    # matplotlib renamed ``labels`` to ``tick_labels`` in 3.9; try the new
    # name first and fall back to the legacy signature for older versions.
    try:
        ax.boxplot(data, tick_labels=labels, showmeans=True)
    except TypeError:  # pragma: no cover - only triggers on matplotlib < 3.9
        ax.boxplot(data, labels=labels, showmeans=True)
    ax.set_xlabel(land_use_col)
    ax.set_ylabel(f"{column} (tC/ha)")
    ax.set_title(title or f"{column} by {land_use_col}")
    ax.grid(True, linestyle="--", alpha=0.4, axis="y")
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    return fig


def plot_depth_profile(
    depths_cm: Iterable[float],
    soc_stocks: Iterable[float],
    title: Optional[str] = None,
    figsize: Tuple[float, float] = _DEFAULT_FIGSIZE,
) -> "Figure":
    """Plot a SOC-vs-depth profile as a line chart with depth inverted.

    Soil-science convention draws depth increasing downward, so the
    y-axis is inverted.

    Parameters
    ----------
    depths_cm:
        Iterable of horizon depths (cm, positive values).
    soc_stocks:
        Iterable of per-horizon SOC stocks (tC/ha) aligned with
        *depths_cm*.
    title:
        Optional plot title.
    figsize:
        Figure size in inches.

    Returns
    -------
    matplotlib.figure.Figure
        The newly-created Figure.

    Raises
    ------
    ImportError
        If matplotlib is not installed.
    ValueError
        If the inputs have mismatched lengths, are empty, or contain
        negative depths.
    """
    depths = np.asarray(list(depths_cm), dtype=float)
    stocks = np.asarray(list(soc_stocks), dtype=float)

    if depths.size == 0 or stocks.size == 0:
        raise ValueError("depths_cm and soc_stocks must be non-empty")
    if depths.size != stocks.size:
        raise ValueError(
            f"depths_cm (n={depths.size}) and soc_stocks (n={stocks.size}) "
            "must have the same length"
        )
    if np.any(depths < 0):
        raise ValueError("depths_cm must contain only non-negative values")

    # Sort by depth so the line chart reads top-down.
    order = np.argsort(depths)
    depths = depths[order]
    stocks = stocks[order]

    plt = _import_matplotlib()
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(stocks, depths, marker="o", linewidth=1.5)
    ax.invert_yaxis()
    ax.set_xlabel("SOC stock (tC/ha)")
    ax.set_ylabel("Depth (cm)")
    ax.set_title(title or "SOC depth profile")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    return fig
