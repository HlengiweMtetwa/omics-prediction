"""Smoke and consistency tests for the synthetic omics demo pipeline.

These verify the pipeline stages are internally consistent (column names,
output paths) rather than validating any scientific claim - the underlying
data is synthetic and has no real predictive signal.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collect_data
import prepare_dataset
import train_model


@pytest.fixture()
def pipeline_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(collect_data, "DATA_DIR", "data")
    monkeypatch.setattr(prepare_dataset, "DATA_DIR", "data")
    monkeypatch.setattr(train_model, "DATA_DIR", "data")
    monkeypatch.setattr(train_model, "MODELS_DIR", "models")
    monkeypatch.setattr(train_model, "RESULTS_DIR", "results")
    os.makedirs("data", exist_ok=True)
    os.makedirs("models", exist_ok=True)
    os.makedirs("results", exist_ok=True)
    return tmp_path


def test_collect_data_writes_expected_files(pipeline_dirs):
    collect_data.simulate_genomic_data()
    collect_data.simulate_protein_data()
    collect_data.simulate_metabolite_data()
    collect_data.simulate_metadata()

    for name in (
        "genomic_features.csv",
        "protein_features.csv",
        "metabolite_features.csv",
        "metadata.csv",
    ):
        assert os.path.exists(os.path.join("data", name))


def test_prepare_dataset_produces_target_column(pipeline_dirs):
    collect_data.simulate_genomic_data()
    collect_data.simulate_protein_data()
    collect_data.simulate_metabolite_data()
    collect_data.simulate_metadata()

    prepare_dataset.prepare_dataset()

    structured = pd.read_csv(os.path.join("data", "structured_dataset.csv"))
    assert "disease_present" in structured.columns
    assert len(structured) == 100
    assert structured.isnull().sum().sum() == 0


def test_train_model_end_to_end(pipeline_dirs):
    collect_data.simulate_genomic_data()
    collect_data.simulate_protein_data()
    collect_data.simulate_metabolite_data()
    collect_data.simulate_metadata()
    prepare_dataset.prepare_dataset()

    train_model.train_and_evaluate()

    assert os.path.exists(os.path.join("models", "random_forest_model.pkl"))
    assert os.path.exists(os.path.join("results", "evaluation_metrics.txt"))
    assert os.path.exists(os.path.join("results", "confusion_matrix.png"))
    assert os.path.exists(os.path.join("results", "feature_importance.png"))

    with open(os.path.join("results", "evaluation_metrics.txt")) as f:
        content = f.read()
    for metric in ("Accuracy", "Precision", "Recall", "F1-score"):
        assert metric in content


def test_dashboard_features_align_with_trained_model(pipeline_dirs):
    """Guards against the exact defect fixed in this pass: the dashboard
    reading a different file/columns than the pipeline actually produces."""
    collect_data.simulate_genomic_data()
    collect_data.simulate_protein_data()
    collect_data.simulate_metabolite_data()
    collect_data.simulate_metadata()
    prepare_dataset.prepare_dataset()
    train_model.train_and_evaluate()

    import joblib

    model = joblib.load(os.path.join("models", "random_forest_model.pkl"))
    data = pd.read_csv(os.path.join("data", "structured_dataset.csv"))
    features = data.drop(columns=["disease_present"])

    assert set(model.feature_names_in_) == set(features.columns)
