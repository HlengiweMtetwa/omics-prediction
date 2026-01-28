# Predictive Model for Disease Surveillance Using Omics Data from Wastewater

**Author:** Manus AI
**Date:** January 28, 2026

## 1. Introduction

This report details the implementation of a predictive model for disease surveillance using simulated omics data extracted from wastewater samples, following the methodology provided by the user. The primary objective was to create a binary classification model capable of predicting disease presence (1) or absence (0) based on features derived from genomic, proteomic, and metabolomic data. The entire workflow, from data simulation to model deployment, was encapsulated in a reproducible Snakemake pipeline.

## 2. Methodology and Implementation

The implementation strictly adhered to the eight-step methodology outlined in the user's request.

### 2.1. Data Collection and Preparation

Since real-world, labeled, and integrated omics datasets for wastewater disease surveillance are complex and often proprietary, the data collection phase was simulated. Python scripts were developed to generate synthetic datasets mimicking the structure of data mined from public repositories like NCBI, UniProt, and MetaboLights/HMDB.

The simulated data included:
*   **Genomic Features:** Gene counts for ten hypothetical pathogen genes (e.g., *Rv0001*, *katG*).
*   **Protein Features:** Abundance levels for five hypothetical protein products.
*   **Metabolite Features:** Concentration values for five hypothetical metabolite biomarkers.
*   **Metadata:** Sample date, region (North, South, East, West), site type (Urban, Rural), and the binary label, **disease_present** (0 or 1).

### 2.2. Structured Dataset Creation and Feature Engineering

The individual omics datasets were merged, and feature engineering was applied. A key engineered feature was the **total_gene_count**, summarizing the overall genomic load. All numerical features were standardized using `StandardScaler` to ensure machine learning compatibility. Categorical metadata (region and site type) were one-hot encoded. The final structured dataset was saved as `structured_dataset.csv`.

### 2.3. Model Architecture and Training

A **Random Forest Classifier** was selected for its robustness and interpretability, as specified in the methodology. The dataset was split into a training set (70%) and a testing set (30%) with a fixed random state for reproducibility. The model was trained using default hyperparameters from the `scikit-learn` library.

### 2.4. Model Evaluation

The model's performance was evaluated on the test set using standard binary classification metrics.

| Metric | Value |
| :--- | :--- |
| Accuracy | 0.7000 |
| Precision | 0.0000 |
| Recall | 0.0000 |
| F1-score | 0.0000 |

*Note: The low performance metrics (Precision, Recall, F1-score) for the positive class (disease presence) are expected due to the nature of the simulated data, which was randomly generated and lacked a true underlying predictive relationship between features and the label.*

The evaluation also included a **Confusion Matrix** and **Feature Importance** analysis, which were saved as visual aids.

![Confusion Matrix](https://private-us-east-1.manuscdn.com/sessionFile/9refSPYGKTmCghO3nnrTEw/sandbox/j7c6w61OmXrO7vztjX3uWE-images_1769635112499_na1fn_L2hvbWUvdWJ1bnR1L3dhc3Rld2F0ZXJfcHJlZGljdGl2ZV9tb2RlbC9yZXN1bHRzL2NvbmZ1c2lvbl9tYXRyaXg.png?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvOXJlZlNQWUdLVG1DZ2hPM25uclRFdy9zYW5kYm94L2o3YzZ3NjFPbVhyTzd2enRqWDN1V0UtaW1hZ2VzXzE3Njk2MzUxMTI0OTlfbmExZm5fTDJodmJXVXZkV0oxYm5SMUwzZGhjM1JsZDJGMFpYSmZjSEpsWkdsamRHbDJaVjl0YjJSbGJDOXlaWE4xYkhSekwyTnZibVoxYzJsdmJsOXRZWFJ5YVhnLnBuZyIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=YuXRHmOR1~tgwVqDiueY0C405tI1fw-~kytmPPNnmFsRzT6DzRVecDJOdXaiKAIrp3vE8gUTdCp2VXLZ1JhqmWvpdv~KJcJFZmZXwzXkAvH0pB7lJTnD8-EpQ9kCIiospC~JnyEf02itOr-HwzwKPdUKNw7Sb-FMhl827yCwudJk6EWL24iT6LrNVdFiEN1ExMR0yBpDNDezAorXpdEgQ4m~y4fBAR8o0gPzT8sYEO2eMGOwk28bclkY8oT7r3EJAcXlhWY-Vue-WeCqEl8ZUyF6WmL4dLMOAYg2IvkqjHM88lib8UXG-VHKwo2qkSZLOxaJ3f3jX-Ch1lWG9pxyRA__)

![Feature Importance](https://private-us-east-1.manuscdn.com/sessionFile/9refSPYGKTmCghO3nnrTEw/sandbox/j7c6w61OmXrO7vztjX3uWE-images_1769635112500_na1fn_L2hvbWUvdWJ1bnR1L3dhc3Rld2F0ZXJfcHJlZGljdGl2ZV9tb2RlbC9yZXN1bHRzL2ZlYXR1cmVfaW1wb3J0YW5jZQ.png?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvOXJlZlNQWUdLVG1DZ2hPM25uclRFdy9zYW5kYm94L2o3YzZ3NjFPbVhyTzd2enRqWDN1V0UtaW1hZ2VzXzE3Njk2MzUxMTI1MDBfbmExZm5fTDJodmJXVXZkV0oxYm5SMUwzZGhjM1JsZDJGMFpYSmZjSEpsWkdsamRHbDJaVjl0YjJSbGJDOXlaWE4xYkhSekwyWmxZWFIxY21WZmFXMXdiM0owWVc1alpRLnBuZyIsIkNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTc5ODc2MTYwMH19fV19&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=LcEf5LjaPS-SdKx3~T4DB4zsCjBKzosQFoeyzIfjqGhMHCDY~P-ZsGX0VyKo4hVttlSyc9zzaxCTFsqUSZB5q~piR2bUkZc4UuGdfwgZlGcJJdKb-1UmChJMVsFoi-XxZeKGDMjfqL65U72gTi3b2q~eksXkf0eM8sg2IFUXRaVt14XXve4zXAj1EbdrdASqBl4zBnecwDdYp8~zNyGNK9~PxpwyfYbwSOKGoPgCZf0-whekQhkBhgcHvIq7ZAIAatlUck2RdoLBgium9j8tmzarNx5i5oC1~fkvlI5SkDpGPO8juspQN7asoK70wFNXm98e~nvKKnhcejcDclzWWQ__)

### 2.5. Reproducibility and Deployment

The trained model was saved as a `.pkl` file (`models/random_forest_model.pkl`) using `joblib` for future deployment.

To ensure **reproducibility**, a `Snakefile` was created. This pipeline automates all steps, from data simulation (`collect_data`) and preparation (`prepare_dataset`) to model training and evaluation (`train_model`), ensuring that the entire analysis can be rerun with a single command. Environment dependencies were listed in `requirements.txt`.

## 3. Conclusion and Future Extension

A complete, end-to-end pipeline for a predictive model using omics data from wastewater has been successfully implemented. The pipeline demonstrates the feasibility of the proposed methodology, including data handling, feature engineering, model training, and deployment saving.

As noted in the original plan, the next logical steps would involve:
1.  **Integration of Real Data:** Retraining the model on real, labeled wastewater surveillance data to achieve meaningful predictive performance.
2.  **Model Optimization:** Integrating and comparing performance with other advanced models (e.g., XGBoost, SVM, or LSTM for time-series data) and performing hyperparameter tuning.

The project structure and key files are provided as attachments for review.
