import os
import pandas as pd
import numpy as np
import requests
from Bio import Entrez
import json

# Set up directories
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def simulate_genomic_data():
    """Simulate genomic features (gene counts) for pathogens."""
    genes = ["Rv0001", "Rv0002", "Rv0003", "Rv0004", "Rv0005", "katG", "inhA", "pncA", "rpoB", "gyrA"]
    samples = 100
    data = np.random.poisson(lam=5, size=(samples, len(genes)))
    df = pd.DataFrame(data, columns=genes)
    df.to_csv(os.path.join(DATA_DIR, "genomic_features.csv"), index=False)
    print("Simulated genomic data saved.")

def simulate_protein_data():
    """Simulate protein annotation data."""
    proteins = ["P9WNK5", "P9WNK3", "P9WNM1", "P9WIB1", "P9WHE3"]
    samples = 100
    data = np.random.normal(loc=10, scale=2, size=(samples, len(proteins)))
    df = pd.DataFrame(data, columns=proteins)
    df.to_csv(os.path.join(DATA_DIR, "protein_features.csv"), index=False)
    print("Simulated protein data saved.")

def simulate_metabolite_data():
    """Simulate metabolite profile data."""
    metabolites = ["M1", "M2", "M3", "M4", "M5"]
    samples = 100
    data = np.random.uniform(low=0, high=100, size=(samples, len(metabolites)))
    df = pd.DataFrame(data, columns=metabolites)
    df.to_csv(os.path.join(DATA_DIR, "metabolite_features.csv"), index=False)
    print("Simulated metabolite data saved.")

def simulate_metadata():
    """Simulate sample metadata."""
    samples = 100
    dates = pd.date_range(start="2023-01-01", periods=samples)
    regions = ["North", "South", "East", "West"]
    site_types = ["Urban", "Rural"]
    
    metadata = {
        "sample_id": range(samples),
        "date": dates,
        "region": np.random.choice(regions, samples),
        "site_type": np.random.choice(site_types, samples),
        "disease_present": np.random.choice([0, 1], samples, p=[0.7, 0.3])
    }
    df = pd.DataFrame(metadata)
    df.to_csv(os.path.join(DATA_DIR, "metadata.csv"), index=False)
    print("Simulated metadata saved.")

if __name__ == "__main__":
    simulate_genomic_data()
    simulate_protein_data()
    simulate_metabolite_data()
    simulate_metadata()
