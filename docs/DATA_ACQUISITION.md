# Obtaining the Raw Data

Third-party datasets are **not redistributed** in this repository. Their
licences differ, and one (the New York Times county series) is non-commercial
only. This document is the retrieval procedure; checksums let you confirm you
obtained the same bytes the published results were computed from.

Place files under `data/raw/` exactly as shown. Then run:

```bash
python -m omics_wbe.cli check-sources
```

---

## 1. CDC National Wastewater Surveillance System (California submissions)

- **Licence:** public domain (US Government work); the mirror used is CC0
- **Landing page:** https://www.kaggle.com/datasets/yashusinghal/master-covid-public-dataset
- **Primary source:** US CDC NWSS. State health departments also publish their own
  submissions; prefer the primary source where available.
- **Destination:** `data/raw/nwss/master-covid-public.csv`
- **SHA-256:** `2a849b1488d1c87b13c4ebe7d15b9c7b460314311ca59204131f2131f63a2956`

Contains 137,711 records, March 2020 – January 2024, 43 California county
groupings, and 11 assay targets that resolve against the project catalogue:
SARS-CoV-2 (N, S, and two variant markers), influenza A and B, RSV, norovirus
GII, mpox (hMPXV), *Candida auris* and *Legionella pneumophila*.

## 2. New York Times COVID-19 US county series

- **Licence:** **CC BY-NC 4.0 — non-commercial use with attribution**
- **Source:** https://github.com/nytimes/covid-19-data (`rolling-averages/`)
- **Destination:** `data/raw/nyt/us-counties-{2020,2021,2022,2023}.csv`

| File | SHA-256 |
|---|---|
| `us-counties-2020.csv` | `85092b05d93d7a3655357a5e46ecd1e8f4615654c1388b40fb53fb8e985e822a` |
| `us-counties-2021.csv` | `91ddd9ee9efcb015d4b5471639a8b10b88f9b21764224e1075e408f68adcd188` |
| `us-counties-2022.csv` | `57f12be7727f79f7d3c5179bced6fc3dcc6036863bc9afa83820f57685f2a809` |
| `us-counties-2023.csv` | `5150ec80d826ec9cecdcac43f736519f83ab38e6a3b707875f1ca1e9f153d321` |

Direct from the NYT repository:

```bash
mkdir -p data/raw/nyt
for year in 2020 2021 2022 2023; do
  curl -L -o "data/raw/nyt/us-counties-${year}.csv" \
    "https://raw.githubusercontent.com/nytimes/covid-19-data/master/rolling-averages/us-counties-${year}.csv"
done
```

## 3. Queensland wastewater surveillance

- **Licence:** CC BY-SA 4.0
- **Landing page:** https://www.kaggle.com/datasets/joebeachcapital/qld-wastewater-surveillance-sars-cov-2-covid19
- **Primary source:** Queensland Government open data portal
- **Destination:** `data/raw/qld/*.csv` (8 quarterly files)

Note: several published quarters are padded to roughly 900,000 all-empty rows by
the spreadsheet they were exported from. The connector drops and counts them
separately from genuine parse failures.

## 4. Verifying

```bash
cd data/raw && find . -name '*.csv' | sort | xargs sha256sum
```

Compare against the tables above. If a checksum differs, the provider has
revised the dataset — record the new checksum and re-run the full pipeline
rather than mixing versions.

## 5. Sequence archives

No files are downloaded from NCBI SRA, ENA or DDBJ. See
`docs/SOP_01_data_acquisition_and_mining.md` §3.4 for why an archive run
inventory is not a measurement dataset, and what read processing would be
required to make it one.
