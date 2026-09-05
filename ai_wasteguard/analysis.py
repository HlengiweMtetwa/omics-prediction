"""Real analysis of an uploaded tabular data file.

Always computes a genuine per-column data profile from the file that was
actually uploaded. Additionally trains and evaluates a real classifier,
but only when the file has a recognizable label column with enough rows
and class variety to do so honestly - never fabricates a metric or
guesses at a label column that isn't there.
"""
from pathlib import Path

import pandas as pd

LABEL_COLUMN_CANDIDATES = ["label", "disease_present", "target", "outcome", "class", "diagnosis"]
MIN_ROWS_FOR_TRAINING = 10


class AnalysisError(Exception):
    pass


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix == ".txt":
        return pd.read_csv(path, sep=None, engine="python")
    if suffix == ".json":
        return pd.read_json(path)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise AnalysisError(f"Don't know how to load tabular data from '{path.name}'.")


def _column_summary(df: pd.DataFrame) -> list[str]:
    lines = ["Column summary:"]
    for col in df.columns:
        series = df[col]
        n_missing = int(series.isna().sum())
        if pd.api.types.is_numeric_dtype(series):
            lines.append(
                f"  {col} (numeric): mean={series.mean():.3f} std={series.std():.3f} "
                f"min={series.min():.3f} max={series.max():.3f} missing={n_missing}"
            )
        else:
            lines.append(f"  {col} (categorical): {series.nunique()} unique values, missing={n_missing}")
    return lines


def analyze_upload(upload_path: Path, models_dir: Path, display_name: str | None = None) -> str:
    """Returns the human-readable analysis report text. Raises
    AnalysisError if the file can't be read at all - never silently
    substitutes a fake result. display_name is what's shown in the report
    (the user's original filename); upload_path (a server-generated
    storage key) is only used to actually locate and read the file."""
    display_name = display_name or upload_path.name
    try:
        df = _read_table(upload_path)
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(f"Could not parse '{display_name}': {exc}") from exc

    if df.empty:
        raise AnalysisError(f"'{display_name}' has no rows to analyze.")

    lines = [
        "REAL DATA ANALYSIS",
        f"Source file: {display_name}",
        f"Rows: {len(df)}  Columns: {len(df.columns)}",
        "",
        *_column_summary(df),
        "",
    ]

    label_col = next((c for c in df.columns if c.lower() in LABEL_COLUMN_CANDIDATES), None)
    if label_col is None:
        lines.append(
            f"No recognized label column found (looked for: {', '.join(LABEL_COLUMN_CANDIDATES)}). "
            "Showing data profile only - no model was trained."
        )
        return "\n".join(lines)

    label_series = df[label_col].dropna()
    n_classes = label_series.nunique()
    if len(df) < MIN_ROWS_FOR_TRAINING or n_classes < 2:
        lines.append(
            f"Found label column '{label_col}' but cannot train a model: need at least "
            f"{MIN_ROWS_FOR_TRAINING} rows and 2 classes (have {len(df)} rows, {n_classes} class(es))."
        )
        return "\n".join(lines)

    feature_cols = [c for c in df.columns if c != label_col and pd.api.types.is_numeric_dtype(df[c])]
    if not feature_cols:
        lines.append(f"Found label column '{label_col}' but no numeric feature columns to train on.")
        return "\n".join(lines)

    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split

    working = df[feature_cols + [label_col]].dropna(subset=[label_col])
    X = working[feature_cols].fillna(working[feature_cols].mean(numeric_only=True))
    y = working[label_col]

    stratify = y if y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=stratify
    )

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, models_dir / "random_forest_model.pkl")

    lines.append(
        f"Trained RandomForestClassifier on label column '{label_col}' using "
        f"{len(feature_cols)} numeric feature column(s): {', '.join(feature_cols)}"
    )
    lines.append(f"Train/test split: {len(X_train)} / {len(X_test)} rows")
    lines.append(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    lines.append(f"Precision: {precision_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
    lines.append(f"Recall: {recall_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
    lines.append(f"F1-score: {f1_score(y_test, y_pred, average='weighted', zero_division=0):.4f}")
    return "\n".join(lines)
