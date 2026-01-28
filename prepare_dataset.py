import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import os

DATA_DIR = "data"

def prepare_dataset():
    # Load simulated datasets
    genomic = pd.read_csv(os.path.join(DATA_DIR, "genomic_features.csv"))
    protein = pd.read_csv(os.path.join(DATA_DIR, "protein_features.csv"))
    metabolite = pd.read_csv(os.path.join(DATA_DIR, "metabolite_features.csv"))
    metadata = pd.read_csv(os.path.join(DATA_DIR, "metadata.csv"))

    # Merge omics data
    omics_data = pd.concat([genomic, protein, metabolite], axis=1)
    
    # Feature Engineering: Summarizing genomic counts
    omics_data['total_gene_count'] = genomic.sum(axis=1)
    
    # Feature Engineering: Scaling
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(omics_data)
    scaled_df = pd.DataFrame(scaled_features, columns=omics_data.columns)
    
    # Combine with metadata labels
    final_df = pd.concat([scaled_df, metadata[['disease_present', 'region', 'site_type']]], axis=1)
    
    # Encode categorical variables
    final_df = pd.get_dummies(final_df, columns=['region', 'site_type'])
    
    # Save structured dataset
    final_df.to_csv(os.path.join(DATA_DIR, "structured_dataset.csv"), index=False)
    print("Structured dataset created and saved.")

if __name__ == "__main__":
    prepare_dataset()
