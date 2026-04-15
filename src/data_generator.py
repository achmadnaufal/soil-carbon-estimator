"""
Synthetic data generator for soil-carbon-estimator.

Produces realistic soil organic carbon datasets for tropical and sub-tropical
field sites.  All functions follow immutable patterns -- they return new
objects and never modify their arguments.

Run directly to write a sample CSV::

    python src/data_generator.py

Author: github.com/achmadnaufal
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLUMNS: Sequence[str] = [
    "sample_id",
    "depth_cm",
    "bulk_density",
    "soc_pct",
    "clay_pct",
    "land_use",
    "plot_id",
]

LAND_USE_CHOICES: Sequence[str] = [
    "tropical_forest",
    "agroforestry",
    "cropland",
    "grassland",
    "peatland",
    "bare_soil",
]

_BASE_DATE = datetime(2023, 1, 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_sample(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate a realistic synthetic soil dataset.

    Produces a new :class:`~pandas.DataFrame` with ``n`` rows.  All
    random values are seeded for reproducibility.  The function never
    mutates its arguments; each call produces a fresh object.

    Parameters
    ----------
    n:
        Number of rows to generate.  Must be a positive integer.
    seed:
        Random seed for NumPy and Python's :mod:`random` module.
        Default is ``42``.

    Returns
    -------
    pd.DataFrame
        DataFrame with the following columns:

        * ``sample_id``   -- string identifier (e.g. ``"SAM001"``)
        * ``depth_cm``    -- sampling depth in centimetres (float)
        * ``bulk_density``-- bulk density in g/cm3 (float)
        * ``soc_pct``     -- soil organic carbon percentage (float)
        * ``clay_pct``    -- clay percentage (float)
        * ``land_use``    -- land use category (str)
        * ``plot_id``     -- plot group identifier (str)

    Raises
    ------
    ValueError
        If *n* is not a positive integer.

    Examples
    --------
    >>> df = generate_sample(10, seed=0)
    >>> len(df)
    10
    >>> set(df.columns) == set(COLUMNS)
    True
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    np.random.seed(seed)
    random.seed(seed)

    n_groups: int = max(5, n // 20)

    data: dict = {}
    for col in COLUMNS:
        if "date" in col:
            data[col] = _generate_date_column(n)
        elif col in ("sample_id", "plot_id") or "code" in col:
            data[col] = [
                f"{col[:3].upper()}{random.randint(1, n_groups):03d}"
                for _ in range(n)
            ]
        elif col == "land_use" or "category" in col or "type" in col or "status" in col:
            data[col] = [random.choice(LAND_USE_CHOICES) for _ in range(n)]
        elif "pct" in col or "rate" in col or "ratio" in col:
            data[col] = np.round(np.random.uniform(0, 100, n), 2).tolist()
        else:
            base = np.random.exponential(100, n)
            noise = np.random.normal(0, 10, n)
            data[col] = np.round(np.abs(base + noise), 2).tolist()

    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _generate_date_column(n: int) -> list[str]:
    """Return a list of *n* random date strings in ``YYYY-MM-DD`` format.

    Dates are uniformly distributed over the year following :data:`_BASE_DATE`.

    Parameters
    ----------
    n:
        Number of date strings to produce.

    Returns
    -------
    list[str]
        List of ISO-formatted date strings.
    """
    return [
        (_BASE_DATE + timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d")
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    Path("data").mkdir(exist_ok=True)
    df = generate_sample(300)
    out_path = "data/sample.csv"
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df)} records -> {out_path}")
    print(df.head())
    print(f"\nShape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
