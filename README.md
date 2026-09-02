# 🔒 EvidenceLock

> **Automated Fact-Checking & Calculation Engine for Business Reports**

EvidenceLock catches false, exaggerated, or misleading numeric claims in business reports by extracting claims and re-calculating them directly against real source data.

---

## 🌟 Key Features

1. **📊 Ground-Truth Data Ingestion (Step 1)**:
   - Upload and preview source CSV datasets (e.g., sales, orders, revenue records).
   - Fast pandas-powered validation and preview.

2. **🔍 NLP Claim Extraction Engine (Step 2)**:
   - Scans unstructured business reports to identify checkable numeric claims.
   - Extracts **Growth % Claims** (e.g. *"Revenue increased by 18%"*) and **Total/Count Claims** (e.g. *"Processed a total of 5,000 orders"*).
   - Filters out vague statements and non-numeric claims.

3. **⚖️ Real-Data Verification Engine (Step 3)**:
   - Computes ground-truth calculations directly from the dataset.
   - Outputs clear color-coded verdicts:
     - 🟩 **CORRECT** (within 1% tolerance)
     - 🟥 **WRONG** (exaggerated or false numbers)
     - 🟨 **UNCLEAR** (ambiguous or insufficient data)
   - Provides clear, transparent plain-English calculation evidence.

4. **📈 Corrected Report & Summary Dashboard (Step 4)**:
   - Automated report correction that replaces incorrect figures with ground-truth numbers.
   - Before/after side-by-side comparison.
   - Summary audit metrics and interactive Chart.js verdict distribution.
   - Downloadable `.txt` corrected business report.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python app.py
```

### 3. Open in Browser
Navigate to `http://127.0.0.1:5000` in your web browser.

---

## 📁 Project Structure

```text
evidencelock/
├── app.py                      # Flask routes and application controller
├── claim_extractor.py          # Regex and NLP claim extraction engine
├── verifier.py                 # Ground-truth verification & report correction logic
├── requirements.txt            # Project dependencies (Flask, Pandas)
├── sample_report.txt           # Sample business report claims
├── samplesuperstore.csv        # Ground-truth sales dataset
├── .gitignore                  # Git ignore rules
└── templates/
    ├── index.html              # 1. Data Ingestion UI
    ├── extract_claims.html      # 2. Claim Extraction UI
    ├── verify_claims.html       # 3. Verification Audit UI
    └── results_dashboard.html   # 4. Corrected Report & Dashboard UI
```
