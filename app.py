import os
import io
import tempfile
import pandas as pd
from flask import Flask, render_template, request, flash, redirect, url_for, Response

# Import custom modules for claim extraction and verification
from claim_extractor import extract_claims
from verifier import verify_claim, generate_corrected_report

# -------------------------------------------------------------
# 1. Base Paths & Flask App Configuration
# We explicitly set the template_folder path to ensure Vercel's
# serverless environment can locate the HTML templates reliably.
# -------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DEFAULT_CSV_PATH = os.path.join(BASE_DIR, "samplesuperstore.csv")
DEFAULT_REPORT_PATH = os.path.join(BASE_DIR, "sample_report.txt")

# Temporary in-memory / /tmp storage path for serverless compatibility
TEMP_CSV_PATH = os.path.join(tempfile.gettempdir(), "evidencelock_active.csv")

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = "evidencelock-hackathon-secret-key"

ALLOWED_EXTENSIONS = {"csv"}

# Fallback sample report text if file reading is restricted
FALLBACK_REPORT_TEXT = """QUARTERLY SALES PERFORMANCE REPORT
Superstore Business Summary

Overview:
This report summarizes our sales performance based on recent order data. Below are the key highlights from our analysis.

1. Revenue Growth
Revenue increased by 18% in the most recent month compared to the previous month.

2. Regional Performance
The West region had the highest total sales among all regions.

3. Order Volume
We processed a total of 5,000 orders during the reported period.

4. Category Performance
The Technology category generated the highest average profit per order.

5. Customer Segment
Corporate customers placed more orders than Consumer customers.

6. Discount Impact
Products with discounts above 20% still generated positive profit on average.

7. Top Performing Product
Office Supplies had the lowest total sales compared to other categories.

8. Shipping Performance
Standard Class was the most frequently used shipping mode.

9. Yearly Trend
Overall annual sales grew by 25% compared to the previous year.

10. General Statement
Our business continues to grow steadily across all regions and categories, driven by consistent customer demand and expanding market reach."""


# -------------------------------------------------------------
# 2. Serverless-Safe Helper Functions
# Handles data streams in-memory and gracefully falls back to
# bundled dataset files when running in read-only environments.
# -------------------------------------------------------------
def allowed_file(filename):
    """Checks if the uploaded file has a .csv extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_active_dataframe():
    """
    Safely retrieves the active DataFrame:
    1. Checks the writable /tmp cache (if user uploaded a custom CSV).
    2. Falls back to bundled samplesuperstore.csv in project root.
    """
    # 1. Try reading temporary uploaded dataset from /tmp
    if os.path.exists(TEMP_CSV_PATH):
        try:
            return pd.read_csv(TEMP_CSV_PATH), "Uploaded CSV (active session)"
        except Exception:
            pass

    # 2. Try reading bundled default dataset
    if os.path.exists(DEFAULT_CSV_PATH):
        try:
            return pd.read_csv(DEFAULT_CSV_PATH), "samplesuperstore.csv (default)"
        except Exception:
            pass

    return None, "No dataset available"


def get_report_text():
    """
    Reads sample_report.txt from disk, falling back to embedded
    text if the filesystem cannot be accessed.
    """
    if os.path.exists(DEFAULT_REPORT_PATH):
        try:
            with open(DEFAULT_REPORT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    return FALLBACK_REPORT_TEXT


# -------------------------------------------------------------
# 3. Route 1: Homepage & CSV Ingestion (Step 1)
# -------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "csv_file" not in request.files:
            flash("No file part was found in the request. Please select a file.", "error")
            return redirect(request.url)

        file = request.files["csv_file"]

        if file.filename == "":
            flash("No file selected. Please choose a CSV file to upload.", "error")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file format. Please upload a CSV file (.csv only).", "error")
            return redirect(request.url)

        try:
            # Read CSV directly from memory stream (works in serverless environments)
            file_bytes = file.read()
            df = pd.read_csv(io.BytesIO(file_bytes))

            if df.empty:
                flash("The uploaded CSV file is empty. Please upload a dataset with data rows.", "warning")
                return redirect(request.url)

            # Safely attempt to cache in /tmp for subsequent verification steps
            try:
                df.to_csv(TEMP_CSV_PATH, index=False)
            except Exception:
                pass  # If /tmp is restricted, operations continue in-memory

            total_rows = len(df)
            total_columns = len(df.columns)
            column_names = df.columns.tolist()

            preview_df = df.head(5).fillna("")
            preview_rows = preview_df.values.tolist()

            return render_template(
                "index.html",
                filename=file.filename,
                total_rows=total_rows,
                total_columns=total_columns,
                columns=column_names,
                rows=preview_rows,
                has_data=True,
                active_page="data"
            )

        except Exception as e:
            flash(f"Could not read the CSV file. Error details: {str(e)}", "error")
            return redirect(request.url)

    return render_template("index.html", has_data=False, active_page="data")


# -------------------------------------------------------------
# 4. Route 2: Claim Extraction Engine (Step 2)
# -------------------------------------------------------------
@app.route("/extract-claims", methods=["GET", "POST"])
def extract_claims_page():
    report_text = get_report_text()

    if request.method == "POST":
        custom_text = request.form.get("report_text", "").strip()
        if custom_text:
            report_text = custom_text

    claims = extract_claims(report_text) if report_text else []

    return render_template(
        "extract_claims.html",
        report_text=report_text,
        claims=claims,
        total_claims=len(claims),
        active_page="claims"
    )


# -------------------------------------------------------------
# 5. Route 3: Claim Verification Engine (Step 3)
# -------------------------------------------------------------
@app.route("/verify-claims", methods=["GET", "POST"])
def verify_claims_page():
    df, dataset_name = get_active_dataframe()
    if df is None:
        flash("No dataset is available for verification. Please upload a CSV first.", "warning")

    report_text = get_report_text()
    if request.method == "POST":
        custom_text = request.form.get("report_text", "").strip()
        if custom_text:
            report_text = custom_text

    extracted_claims = extract_claims(report_text) if report_text else []

    verification_results = []
    if df is not None:
        for claim in extracted_claims:
            res = verify_claim(claim, df)
            verification_results.append(res)
    else:
        for claim in extracted_claims:
            verification_results.append({
                "original_sentence": claim.get("original_sentence", ""),
                "verdict": "UNCLEAR",
                "claimed_value": claim.get("claimed_value"),
                "real_value": None,
                "evidence": "No dataset loaded to perform calculations."
            })

    correct_count = sum(1 for r in verification_results if r["verdict"] == "CORRECT")
    wrong_count = sum(1 for r in verification_results if r["verdict"] == "WRONG")
    unclear_count = sum(1 for r in verification_results if r["verdict"] == "UNCLEAR")

    return render_template(
        "verify_claims.html",
        results=verification_results,
        dataset_name=dataset_name,
        total_claims=len(verification_results),
        correct_count=correct_count,
        wrong_count=wrong_count,
        unclear_count=unclear_count,
        active_page="verify"
    )


# -------------------------------------------------------------
# 6. Route 4: Final Corrected Report & Summary Dashboard (Step 4)
# -------------------------------------------------------------
@app.route("/results-dashboard", methods=["GET", "POST"])
def results_dashboard():
    df, dataset_name = get_active_dataframe()
    original_report_text = get_report_text()

    if request.method == "POST":
        custom_text = request.form.get("report_text", "").strip()
        if custom_text:
            original_report_text = custom_text

    extracted_claims = extract_claims(original_report_text) if original_report_text else []
    verification_results = []
    if df is not None:
        for claim in extracted_claims:
            verification_results.append(verify_claim(claim, df))

    corrected_report_text = generate_corrected_report(original_report_text, verification_results)

    total_claims = len(verification_results)
    correct_count = sum(1 for r in verification_results if r["verdict"] == "CORRECT")
    wrong_count = sum(1 for r in verification_results if r["verdict"] == "WRONG")
    unclear_count = sum(1 for r in verification_results if r["verdict"] == "UNCLEAR")

    evaluated_claims = correct_count + wrong_count
    accuracy_rate = round((correct_count / evaluated_claims) * 100, 1) if evaluated_claims > 0 else 0.0

    return render_template(
        "results_dashboard.html",
        original_report_text=original_report_text,
        corrected_report_text=corrected_report_text,
        dataset_name=dataset_name,
        total_claims=total_claims,
        correct_count=correct_count,
        wrong_count=wrong_count,
        unclear_count=unclear_count,
        accuracy_rate=accuracy_rate,
        verification_results=verification_results,
        active_page="dashboard"
    )


# -------------------------------------------------------------
# 7. Route 5: In-Memory Download of Corrected Report (.txt)
# Generates the file stream directly in memory without disk access.
# -------------------------------------------------------------
@app.route("/download-corrected-report")
def download_corrected_report():
    df, _ = get_active_dataframe()
    original_report_text = get_report_text()

    extracted_claims = extract_claims(original_report_text) if original_report_text else []
    verification_results = []
    if df is not None:
        for claim in extracted_claims:
            verification_results.append(verify_claim(claim, df))

    corrected_report_text = generate_corrected_report(original_report_text, verification_results)

    # In-memory stream response
    return Response(
        corrected_report_text,
        mimetype="text/plain",
        headers={
            "Content-Disposition": "attachment;filename=corrected_business_report.txt",
            "Content-Type": "text/plain; charset=utf-8"
        }
    )


# -------------------------------------------------------------
# 8. Local Application Entry Point
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
