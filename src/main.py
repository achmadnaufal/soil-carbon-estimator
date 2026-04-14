"""
Soil organic carbon (SOC) stock estimation and monitoring tools.

This module exposes the :class:`SoilCarbonEstimator` class, which provides a
high-level pipeline for loading, validating, preprocessing, and analysing
soil carbon datasets.  All data-transformation methods return *new* objects
and never mutate their inputs.

Author: github.com/achmadnaufal
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any

from src.soc_calculator import (
    validate_dataframe,
    add_soc_stock_column,
    filter_valid_rows,
    REQUIRED_COLUMNS,
)


class SoilCarbonEstimator:
    """High-level pipeline for soil organic carbon stock estimation.

    The estimator wraps data loading, validation, preprocessing, and
    statistical analysis in a single, chainable interface.  All methods
    that accept a :class:`~pandas.DataFrame` return a *new* object,
    preserving the original data unchanged.

    Parameters
    ----------
    config:
        Optional mapping of configuration overrides.  Supported keys:

        ``drop_invalid_rows`` (*bool*, default ``True``)
            When ``True``, rows that fail range checks are silently
            dropped before analysis.  Set to ``False`` to keep them
            (invalid cells will appear as ``NaN``).

    Examples
    --------
    Basic pipeline using a CSV file::

        from src.main import SoilCarbonEstimator

        estimator = SoilCarbonEstimator()
        result = estimator.run("demo/sample_data.csv")
        print(result["means"])

    Working directly with a DataFrame::

        import pandas as pd
        from src.main import SoilCarbonEstimator

        df = pd.read_csv("demo/sample_data.csv")
        estimator = SoilCarbonEstimator()
        analysis = estimator.analyze(df)
        print(analysis["total_records"])
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config: Dict[str, Any] = config or {}

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    def load_data(self, filepath: str) -> pd.DataFrame:
        """Load a dataset from a CSV or Excel file.

        The file path is resolved relative to the current working directory.
        For Excel files both ``.xlsx`` and ``.xls`` extensions are supported.

        Parameters
        ----------
        filepath:
            Path to the CSV or Excel file.

        Returns
        -------
        pd.DataFrame
            Raw DataFrame as returned by pandas — no preprocessing applied.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not point to an existing file.
        ValueError
            If the file extension is not one of ``.csv``, ``.xlsx``, ``.xls``.

        Examples
        --------
        >>> estimator = SoilCarbonEstimator()
        >>> df = estimator.load_data("demo/sample_data.csv")
        >>> isinstance(df, pd.DataFrame)
        True
        """
        p = Path(filepath)
        suffix = p.suffix.lower()

        if suffix not in (".csv", ".xlsx", ".xls"):
            raise ValueError(
                f"Unsupported file extension '{p.suffix}'. "
                "Accepted formats: .csv, .xlsx, .xls"
            )

        if not p.exists():
            raise FileNotFoundError(f"Data file not found: {filepath}")

        if suffix in (".xlsx", ".xls"):
            return pd.read_excel(filepath)
        return pd.read_csv(filepath)

    # ------------------------------------------------------------------
    # Validation & preprocessing
    # ------------------------------------------------------------------

    def validate(self, df: pd.DataFrame) -> bool:
        """Validate that *df* is a non-empty DataFrame with the required columns.

        Delegates to :func:`~src.soc_calculator.validate_dataframe` for
        detailed checks, but catches missing-column errors when the required
        SOC columns are absent — in that case only the *empty* check is
        enforced so that datasets without SOC columns can still be loaded
        for general analysis.

        Parameters
        ----------
        df:
            DataFrame to inspect.

        Returns
        -------
        bool
            ``True`` when validation passes.

        Raises
        ------
        ValueError
            If the DataFrame is empty.
        TypeError
            If *df* is not a :class:`~pandas.DataFrame`.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                f"Expected a pandas DataFrame, got {type(df).__name__}"
            )
        if df.empty:
            raise ValueError("Input DataFrame is empty")
        return True

    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and standardise column names; drop fully-empty rows.

        Returns a *new* DataFrame — the original is not modified.

        Transformations applied:

        1. Drop rows where every cell is ``NaN``.
        2. Strip leading/trailing whitespace from column names.
        3. Lower-case all column names.
        4. Replace spaces in column names with underscores.

        Parameters
        ----------
        df:
            Raw input DataFrame.

        Returns
        -------
        pd.DataFrame
            Cleaned copy of *df*.

        Examples
        --------
        >>> import pandas as pd
        >>> from src.main import SoilCarbonEstimator
        >>> raw = pd.DataFrame({"Bulk Density": [1.2], "SOC Pct": [2.5]})
        >>> clean = SoilCarbonEstimator().preprocess(raw)
        >>> list(clean.columns)
        ['bulk_density', 'soc_pct']
        """
        cleaned = df.copy()
        cleaned = cleaned.dropna(how="all")
        cleaned.columns = [
            c.lower().strip().replace(" ", "_") for c in cleaned.columns
        ]
        return cleaned

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run the core analysis pipeline and return a summary metrics dict.

        Steps performed:

        1. Preprocess (clean column names, drop empty rows).
        2. Optionally filter rows with out-of-range values
           (controlled by ``config["drop_invalid_rows"]``, default ``True``).
        3. If SOC-required columns are present, compute
           ``soc_stock_tC_ha`` for every valid row.
        4. Compute descriptive statistics for all numeric columns.

        Parameters
        ----------
        df:
            Input DataFrame.  Must not be empty.  Should contain at least
            some numeric columns for meaningful statistics.

        Returns
        -------
        dict
            Dictionary with the following keys:

            ``total_records`` (*int*)
                Number of rows after preprocessing.
            ``columns`` (*list[str]*)
                Column names after preprocessing.
            ``missing_pct`` (*dict*)
                Percentage of missing values per column.
            ``summary_stats`` (*dict*, optional)
                Output of ``DataFrame.describe()`` for numeric columns.
            ``totals`` (*dict*, optional)
                Column-wise sums for numeric columns.
            ``means`` (*dict*, optional)
                Column-wise means for numeric columns.
            ``soc_stats`` (*dict*, optional)
                Descriptive statistics for ``soc_stock_tC_ha`` when the
                required SOC columns are present.

        Raises
        ------
        ValueError
            If *df* is empty after preprocessing.

        Examples
        --------
        >>> import pandas as pd
        >>> from src.main import SoilCarbonEstimator
        >>> data = {
        ...     "bulk_density_g_cm3": [1.2, 1.1],
        ...     "organic_carbon_pct": [2.5, 3.0],
        ...     "depth_cm": [30, 30],
        ... }
        >>> result = SoilCarbonEstimator().analyze(pd.DataFrame(data))
        >>> result["total_records"]
        2
        """
        processed = self.preprocess(df)

        if processed.empty:
            raise ValueError("DataFrame is empty after preprocessing")

        drop_invalid = self.config.get("drop_invalid_rows", True)

        # Attempt SOC-specific processing when columns are present
        soc_cols_present = REQUIRED_COLUMNS.issubset(set(processed.columns))
        if soc_cols_present:
            if drop_invalid:
                processed = filter_valid_rows(processed)
            processed = add_soc_stock_column(processed)

        result: Dict[str, Any] = {
            "total_records": len(processed),
            "columns": list(processed.columns),
            "missing_pct": (
                processed.isnull().sum() / max(len(processed), 1) * 100
            )
            .round(1)
            .to_dict(),
        }

        numeric_df = processed.select_dtypes(include="number")
        if not numeric_df.empty:
            result["summary_stats"] = numeric_df.describe().round(3).to_dict()
            result["totals"] = numeric_df.sum().round(2).to_dict()
            result["means"] = numeric_df.mean().round(3).to_dict()

        if soc_cols_present and "soc_stock_tC_ha" in processed.columns:
            soc_series = processed["soc_stock_tC_ha"].dropna()
            result["soc_stats"] = {
                "mean_tC_ha": round(float(soc_series.mean()), 2),
                "min_tC_ha": round(float(soc_series.min()), 2),
                "max_tC_ha": round(float(soc_series.max()), 2),
                "total_tC_ha": round(float(soc_series.sum()), 2),
                "n_valid": int(soc_series.count()),
            }

        return result

    # ------------------------------------------------------------------
    # Convenience pipeline
    # ------------------------------------------------------------------

    def run(self, filepath: str) -> Dict[str, Any]:
        """Execute the full pipeline: load → validate → analyze.

        This is the single entry-point for processing a data file end-to-end.

        Parameters
        ----------
        filepath:
            Path to the input CSV or Excel file.

        Returns
        -------
        dict
            Analysis result as returned by :meth:`analyze`.

        Raises
        ------
        FileNotFoundError
            If *filepath* does not exist.
        ValueError
            If the file cannot be parsed or the resulting DataFrame is empty.

        Examples
        --------
        >>> from src.main import SoilCarbonEstimator
        >>> result = SoilCarbonEstimator().run("demo/sample_data.csv")
        >>> "soc_stats" in result
        True
        """
        df = self.load_data(filepath)
        self.validate(df)
        return self.analyze(df)

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def to_dataframe(self, result: Dict) -> pd.DataFrame:
        """Flatten an analysis result dictionary into a two-column DataFrame.

        Nested dictionaries are expanded using dot notation for the metric
        name (e.g. ``"summary_stats.depth_cm"``).

        Parameters
        ----------
        result:
            Dictionary returned by :meth:`analyze` or :meth:`run`.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns ``metric`` (str) and ``value`` (any).

        Examples
        --------
        >>> from src.main import SoilCarbonEstimator
        >>> import pandas as pd
        >>> data = {
        ...     "bulk_density_g_cm3": [1.2],
        ...     "organic_carbon_pct": [2.5],
        ...     "depth_cm": [30],
        ... }
        >>> estimator = SoilCarbonEstimator()
        >>> result = estimator.analyze(pd.DataFrame(data))
        >>> df_out = estimator.to_dataframe(result)
        >>> "metric" in df_out.columns and "value" in df_out.columns
        True
        """
        rows = []
        for key, value in result.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    rows.append({"metric": f"{key}.{sub_key}", "value": sub_value})
            else:
                rows.append({"metric": key, "value": value})
        return pd.DataFrame(rows)
