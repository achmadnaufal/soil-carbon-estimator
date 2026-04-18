"""Tests for the :mod:`src.plotting` helper functions."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Skip the whole module when matplotlib is not available - plotting is an
# optional dependency.
matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg", force=False)

from src.plotting import (  # noqa: E402
    _choose_bin_count,
    plot_depth_profile,
    plot_soc_by_land_use,
    plot_soc_histogram,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def soc_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": list("ABCDEFGH"),
            "soc_stock_tC_ha": [50.0, 62.0, 78.0, 81.0, 95.0, 45.0, 70.0, 88.0],
            "land_use": [
                "cropland",
                "cropland",
                "tropical_forest",
                "tropical_forest",
                "tropical_forest",
                "grassland",
                "grassland",
                "agroforestry",
            ],
        }
    )


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


def test_choose_bin_count_clamped() -> None:
    assert _choose_bin_count(0) == 5
    assert _choose_bin_count(4) >= 5
    assert _choose_bin_count(10_000) <= 40


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


def test_histogram_returns_figure(soc_df: pd.DataFrame) -> None:
    fig = plot_soc_histogram(soc_df)
    # Basic sanity: exactly one Axes and the x-label names the column.
    assert len(fig.axes) == 1
    ax = fig.axes[0]
    assert "soc_stock_tC_ha" in ax.get_xlabel()


def test_histogram_raises_on_empty_dataframe() -> None:
    with pytest.raises(ValueError, match="empty"):
        plot_soc_histogram(pd.DataFrame({"soc_stock_tC_ha": []}))


def test_histogram_raises_when_column_missing(soc_df: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="not found"):
        plot_soc_histogram(soc_df.drop(columns=["soc_stock_tC_ha"]))


def test_histogram_raises_when_all_nan() -> None:
    df = pd.DataFrame({"soc_stock_tC_ha": [None, None, None]})
    with pytest.raises(ValueError, match="no finite"):
        plot_soc_histogram(df)


# ---------------------------------------------------------------------------
# Land-use boxplot
# ---------------------------------------------------------------------------


def test_boxplot_by_land_use_returns_figure(soc_df: pd.DataFrame) -> None:
    fig = plot_soc_by_land_use(soc_df)
    ax = fig.axes[0]
    tick_labels = [t.get_text() for t in ax.get_xticklabels()]
    # All distinct land-use labels must appear on the x-axis.
    for label in soc_df["land_use"].unique():
        assert label in tick_labels


def test_boxplot_raises_when_column_missing(soc_df: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="land_use"):
        plot_soc_by_land_use(soc_df.drop(columns=["land_use"]))


# ---------------------------------------------------------------------------
# Depth profile
# ---------------------------------------------------------------------------


def test_depth_profile_inverts_y_axis() -> None:
    fig = plot_depth_profile([10, 20, 40], [25.0, 22.0, 18.0])
    ax = fig.axes[0]
    y_low, y_high = ax.get_ylim()
    # y-axis is inverted so the lower ylim should exceed the upper ylim.
    assert y_low > y_high


def test_depth_profile_validates_length_mismatch() -> None:
    with pytest.raises(ValueError, match="same length"):
        plot_depth_profile([10, 20], [5.0, 4.0, 3.0])


def test_depth_profile_rejects_negative_depth() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        plot_depth_profile([-1, 10, 20], [1.0, 2.0, 3.0])
