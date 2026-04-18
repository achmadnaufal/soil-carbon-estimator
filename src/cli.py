"""
Command-line interface for the soil carbon estimator.

Provides a single entry-point ``soil-carbon`` (or ``python -m src.cli``) with
sub-commands for the most common analyst workflows:

* ``analyze``      - Run the full pipeline on a CSV/Excel file and print or
                     export the resulting summary metrics.
* ``harmonise``    - Harmonise a long-format profile dataset to a reference
                     depth (default 30 cm) and write the result to CSV.
* ``stock-change`` - Compare two epochs (baseline vs. monitoring) and emit a
                     stock-change summary.
* ``generate``     - Create a synthetic demo dataset for quick experiments.

All sub-commands follow the immutable-data contract of the library - they
never mutate user input and always emit explicit files or stdout.

Author: github.com/achmadnaufal
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from src.depth_profile import harmonise_to_reference_depth
from src.main import SoilCarbonEstimator
from src.stock_change_calculator import compute_stock_change, summarise_stock_change


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_table(path: str) -> pd.DataFrame:
    """Read a CSV or Excel file, raising a friendly error on failure.

    Parameters
    ----------
    path:
        Filesystem path to the input file.

    Returns
    -------
    pd.DataFrame
        Parsed DataFrame.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file extension is not recognised.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(p)
    raise ValueError(
        f"Unsupported file extension '{suffix}'. Expected .csv/.xlsx/.xls"
    )


def _write_output(df: pd.DataFrame, output: Optional[str]) -> None:
    """Write *df* to *output* (CSV) or to stdout when *output* is ``None``.

    Parameters
    ----------
    df:
        DataFrame to emit.
    output:
        Destination CSV path.  When ``None`` the DataFrame is printed to
        stdout using ``to_csv(index=False)``.
    """
    if output is None:
        df.to_csv(sys.stdout, index=False)
        return
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def cmd_analyze(args: argparse.Namespace) -> int:
    """Handle the ``analyze`` sub-command.

    Runs the full :class:`SoilCarbonEstimator` pipeline on an input CSV/Excel
    file and writes the resulting summary metrics to *args.output* (or stdout).

    Parameters
    ----------
    args:
        Parsed arguments - expects ``input`` and ``output`` attributes, plus
        a boolean ``keep_invalid`` flag.

    Returns
    -------
    int
        ``0`` on success, non-zero on handled error.
    """
    config = {"drop_invalid_rows": not args.keep_invalid}
    estimator = SoilCarbonEstimator(config=config)
    result = estimator.run(args.input)

    if args.format == "json":
        text = json.dumps(result, indent=2, default=str)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(text)
        else:
            sys.stdout.write(text + "\n")
        return 0

    # default: csv (flattened)
    df_out = estimator.to_dataframe(result)
    _write_output(df_out, args.output)
    return 0


def cmd_harmonise(args: argparse.Namespace) -> int:
    """Handle the ``harmonise`` sub-command.

    Loads a long-format profile dataset and delegates to
    :func:`harmonise_to_reference_depth`, writing the per-site result to CSV.
    """
    df = _read_table(args.input)
    harmonised = harmonise_to_reference_depth(
        df,
        target_depth_cm=args.depth,
        extrapolate=not args.no_extrapolate,
    )
    _write_output(harmonised, args.output)
    return 0


def cmd_stock_change(args: argparse.Namespace) -> int:
    """Handle the ``stock-change`` sub-command.

    Reads two per-site SOC-stock tables (baseline and monitoring epochs),
    joins them on ``site_id``, and emits a stock-change summary (per-site
    or aggregated).
    """
    baseline = _read_table(args.baseline)
    monitoring = _read_table(args.monitoring)
    per_site = compute_stock_change(
        baseline, monitoring, years_elapsed=args.years
    )

    if args.aggregate:
        summary = summarise_stock_change(per_site, years_elapsed=args.years)
        df_out = pd.DataFrame([asdict(summary)])
    else:
        df_out = per_site

    _write_output(df_out, args.output)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Handle the ``generate`` sub-command.

    Creates a synthetic SOC dataset using :mod:`src.data_generator` and
    writes it to *args.output*.
    """
    # Import here so the dependency is only required on demand.
    from src.data_generator import generate_sample

    df = generate_sample(n=args.rows, seed=args.seed)
    _write_output(df, args.output)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``argparse`` parser for the CLI.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser with all sub-commands attached.
    """
    parser = argparse.ArgumentParser(
        prog="soil-carbon",
        description=(
            "Soil organic carbon (SOC) stock estimation and monitoring CLI. "
            "Run sub-commands with --help for details."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze ----------------------------------------------------------------
    p_analyze = sub.add_parser(
        "analyze", help="Run the full estimation pipeline on an input file."
    )
    p_analyze.add_argument("input", help="CSV or Excel file with soil samples.")
    p_analyze.add_argument(
        "-o", "--output", default=None, help="Destination file (default: stdout)."
    )
    p_analyze.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="Output format when emitting to stdout or file.",
    )
    p_analyze.add_argument(
        "--keep-invalid",
        action="store_true",
        help="Keep rows with out-of-range values (default: drop).",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    # harmonise --------------------------------------------------------------
    p_harm = sub.add_parser(
        "harmonise",
        help="Harmonise long-format profile data to a reference depth.",
    )
    p_harm.add_argument("input", help="Long-format profile CSV (per-horizon rows).")
    p_harm.add_argument(
        "-o", "--output", default=None, help="Destination CSV (default: stdout)."
    )
    p_harm.add_argument(
        "--depth",
        type=float,
        default=30.0,
        help="Reference depth in cm (default: 30).",
    )
    p_harm.add_argument(
        "--no-extrapolate",
        action="store_true",
        help="Disable exponential extrapolation beyond the deepest horizon.",
    )
    p_harm.set_defaults(func=cmd_harmonise)

    # stock-change -----------------------------------------------------------
    p_sc = sub.add_parser(
        "stock-change",
        help="Compare baseline vs monitoring SOC stocks per site.",
    )
    p_sc.add_argument("baseline", help="CSV with baseline site stocks.")
    p_sc.add_argument("monitoring", help="CSV with monitoring site stocks.")
    p_sc.add_argument(
        "-o", "--output", default=None, help="Destination CSV (default: stdout)."
    )
    p_sc.add_argument(
        "--years",
        type=float,
        required=True,
        help="Years elapsed between baseline and monitoring surveys.",
    )
    p_sc.add_argument(
        "--aggregate",
        action="store_true",
        help="Emit a single-row aggregate summary instead of per-site rows.",
    )
    p_sc.set_defaults(func=cmd_stock_change)

    # generate ---------------------------------------------------------------
    p_gen = sub.add_parser(
        "generate",
        help="Create a synthetic SOC dataset for demos or testing.",
    )
    p_gen.add_argument(
        "-o", "--output", default=None, help="Destination CSV (default: stdout)."
    )
    p_gen.add_argument("--rows", type=int, default=20, help="Number of rows.")
    p_gen.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility."
    )
    p_gen.set_defaults(func=cmd_generate)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry-point used by both ``python -m src.cli`` and console_scripts.

    Parameters
    ----------
    argv:
        Optional list of arguments (for testing).  ``None`` means
        ``sys.argv[1:]``.

    Returns
    -------
    int
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args) or 0)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
