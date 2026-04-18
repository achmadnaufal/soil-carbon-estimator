"""Tests for the :mod:`src.cli` command-line interface."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure the package under test is importable when invoked via `pytest`
# from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cli import build_parser, main  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """Write a small, valid SOC dataset to a temporary CSV and return its path."""
    df = pd.DataFrame(
        {
            "site_id": ["A", "B", "C"],
            "bulk_density_g_cm3": [1.2, 1.1, 1.3],
            "organic_carbon_pct": [2.5, 3.0, 1.8],
            "depth_cm": [30, 30, 30],
            "land_use": ["cropland", "tropical_forest", "grassland"],
        }
    )
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture()
def profile_csv(tmp_path: Path) -> Path:
    """Write a long-format profile dataset with three horizons per site."""
    rows = []
    for site in ("S1", "S2"):
        for depth, stock in [(10, 25.0), (20, 22.0), (40, 18.0)]:
            rows.append(
                {
                    "site_id": site,
                    "depth_cm": depth,
                    "soc_stock_tC_ha": stock,
                }
            )
    path = tmp_path / "profile.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Parser smoke tests
# ---------------------------------------------------------------------------


def test_build_parser_exposes_all_subcommands() -> None:
    parser = build_parser()
    # Trigger the sub-parser registration and extract command names.
    sub = next(
        action for action in parser._actions if action.dest == "command"
    )
    assert set(sub.choices.keys()) == {
        "analyze",
        "harmonise",
        "stock-change",
        "generate",
    }


def test_missing_subcommand_exits_nonzero(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit):
        main([])


# ---------------------------------------------------------------------------
# analyze sub-command
# ---------------------------------------------------------------------------


def test_analyze_json_to_file(tmp_path: Path, sample_csv: Path) -> None:
    out = tmp_path / "report.json"
    exit_code = main(
        ["analyze", str(sample_csv), "-o", str(out), "--format", "json"]
    )
    assert exit_code == 0
    payload = json.loads(out.read_text())
    assert payload["total_records"] == 3
    assert "soc_stats" in payload
    assert payload["soc_stats"]["n_valid"] == 3


def test_analyze_csv_stdout(
    sample_csv: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code = main(["analyze", str(sample_csv)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "metric" in captured.out and "value" in captured.out


def test_analyze_missing_file_returns_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    missing = tmp_path / "does-not-exist.csv"
    exit_code = main(["analyze", str(missing)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error" in captured.err


# ---------------------------------------------------------------------------
# harmonise sub-command
# ---------------------------------------------------------------------------


def test_harmonise_produces_one_row_per_site(
    tmp_path: Path, profile_csv: Path
) -> None:
    out = tmp_path / "harmonised.csv"
    exit_code = main(
        [
            "harmonise",
            str(profile_csv),
            "-o",
            str(out),
            "--depth",
            "30",
        ]
    )
    assert exit_code == 0
    result = pd.read_csv(out)
    assert set(result["site_id"]) == {"S1", "S2"}
    assert "soc_stock_tC_ha" in result.columns
    assert (result["reference_depth_cm"] == 30.0).all()


# ---------------------------------------------------------------------------
# stock-change sub-command
# ---------------------------------------------------------------------------


def test_stock_change_aggregate(tmp_path: Path) -> None:
    baseline = tmp_path / "t0.csv"
    monitoring = tmp_path / "t1.csv"
    pd.DataFrame(
        {"site_id": ["X", "Y"], "soc_stock_tC_ha": [80.0, 60.0]}
    ).to_csv(baseline, index=False)
    pd.DataFrame(
        {"site_id": ["X", "Y"], "soc_stock_tC_ha": [88.0, 66.0]}
    ).to_csv(monitoring, index=False)

    out = tmp_path / "summary.csv"
    exit_code = main(
        [
            "stock-change",
            str(baseline),
            str(monitoring),
            "-o",
            str(out),
            "--years",
            "4",
            "--aggregate",
        ]
    )
    assert exit_code == 0
    result = pd.read_csv(out)
    assert len(result) == 1
    assert result.iloc[0]["n_sites"] == 2
    # Both sites gained 6-8 tC/ha over 4 years => positive mean delta.
    assert result.iloc[0]["mean_delta_tC_ha"] > 0


# ---------------------------------------------------------------------------
# generate sub-command
# ---------------------------------------------------------------------------


def test_generate_writes_expected_row_count(tmp_path: Path) -> None:
    out = tmp_path / "synthetic.csv"
    exit_code = main(
        ["generate", "-o", str(out), "--rows", "7", "--seed", "123"]
    )
    assert exit_code == 0
    df = pd.read_csv(out)
    assert len(df) == 7
    # Generator always emits at least a sample/plot identifier and a depth.
    assert "depth_cm" in df.columns
    assert not df.empty
