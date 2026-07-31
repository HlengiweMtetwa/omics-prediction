import streamlit as st
import pandas as pd
import joblib
from PIL import Image

st.set_page_config(page_title="Omics Disease Predictor", layout="centered")

st.title("🔬 Omics-Based Disease Prediction Dashboard")
st.write(
    "This app visualizes a predictive model trained on gene, protein, and "
    "metabolite features derived from wastewater samples."
)

st.warning(
    "⚠️ **Demonstration prototype — synthetic data only.** The genomic, "
    "protein, metabolite and metadata inputs used here are randomly "
    "generated for methodology demonstration purposes; they are not real "
    "surveillance measurements. The trained model has no genuine predictive "
    "signal (precision/recall on the synthetic label are effectively zero) "
    "and outputs shown below must not be interpreted as an environmental "
    "disease signal, a risk assessment, or a public-health finding."
)

MODEL_PATH = "models/random_forest_model.pkl"
DATA_PATH = "data/structured_dataset.csv"
TARGET_COLUMN = "disease_present"

try:
    model = joblib.load(MODEL_PATH)
    data = pd.read_csv(DATA_PATH)
except FileNotFoundError as exc:
    st.error(
        f"Required file not found: {exc.filename}. "
        "Run the pipeline first (`snakemake` or the individual scripts: "
        "collect_data.py -> prepare_dataset.py -> train_model.py)."
    )
    st.stop()

if TARGET_COLUMN not in data.columns:
    st.error(f"Expected target column '{TARGET_COLUMN}' not found in {DATA_PATH}.")
    st.stop()

features = data.drop(columns=[TARGET_COLUMN])
labels = data[TARGET_COLUMN]

if st.checkbox("Show raw data"):
    st.dataframe(data.head())

missing_features = set(model.feature_names_in_) - set(features.columns)
if missing_features:
    st.error(
        "The loaded model was trained on features that are not present in "
        f"the current dataset: {sorted(missing_features)}. Retrain the "
        "model against the current dataset before predicting."
    )
    st.stop()

predictions = model.predict(features[model.feature_names_in_])
data["Prediction"] = predictions

st.subheader("📊 Prediction Summary")
st.write(data["Prediction"].value_counts().rename({0: "No Disease", 1: "Disease"}))

st.subheader("📈 Feature Importance")
try:
    img = Image.open("results/feature_importance.png")
    st.image(img, caption="Top Features", use_container_width=True)
except FileNotFoundError:
    st.warning("Feature importance plot not found. Run train_model.py to generate it.")

st.subheader("📉 Confusion Matrix")
try:
    img2 = Image.open("results/confusion_matrix.png")
    st.image(img2, caption="Confusion Matrix", use_container_width=True)
except FileNotFoundError:
    st.warning("Confusion matrix image not found. Run train_model.py to generate it.")

st.success("✅ Dashboard Loaded Successfully.")
