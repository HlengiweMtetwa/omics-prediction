# Snakemake pipeline for Wastewater Predictive Model

rule all:
    input:
        "results/evaluation_metrics.txt",
        "results/confusion_matrix.png",
        "results/feature_importance.png",
        "models/random_forest_model.pkl"

rule collect_data:
    output:
        "data/genomic_features.csv",
        "data/protein_features.csv",
        "data/metabolite_features.csv",
        "data/metadata.csv"
    script:
        "scripts/collect_data.py"

rule prepare_dataset:
    input:
        "data/genomic_features.csv",
        "data/protein_features.csv",
        "data/metabolite_features.csv",
        "data/metadata.csv"
    output:
        "data/structured_dataset.csv"
    script:
        "scripts/prepare_dataset.py"

rule train_model:
    input:
        "data/structured_dataset.csv"
    output:
        "results/evaluation_metrics.txt",
        "results/confusion_matrix.png",
        "results/feature_importance.png",
        "models/random_forest_model.pkl"
    script:
        "scripts/train_model.py"
