import streamlit as st
import pandas as pd
import joblib
import matplotlib.pyplot as plt
from PIL import Image

st.set_page_config(page_title="Omics Disease Predictor", layout="centered")

st.title("🔬 Omics-Based Disease Prediction Dashboard")
st.write("This app visualizes the predictive model trained on gene, protein, and metabolite data from wastewater samples.")

model = joblib.load("models/random_forest_model.pkl")
data = pd.read_csv("data/processed/final_model_input.csv")
features = data[["gene_feature", "protein_feature", "metabolite_feature"]]
labels = data["disease_presence"]

if st.checkbox("Show raw data"):
    st.dataframe(data.head())

predictions = model.predict(features)
data["Prediction"] = predictions

st.subheader("📊 Prediction Summary")
st.write(data["Prediction"].value_counts().rename({0: "No Disease", 1: "Disease"}))

st.subheader("📈 Feature Importance")
try:
    img = Image.open("feature_importance.png")
    st.image(img, caption="Top Features", use_column_width=True)
except:
    st.warning("Feature importance plot not found.")

st.subheader("📉 Confusion Matrix")
try:
    img2 = Image.open("confusion_matrix.png")
    st.image(img2, caption="Confusion Matrix", use_column_width=True)
except:
    st.warning("Confusion matrix image not found.")

st.success("✅ Dashboard Loaded Successfully.")
