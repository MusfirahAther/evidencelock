import os
import io
import pandas as pd
from flask import Flask, render_template, request, flash, redirect, url_for, Response

# Import our custom modules for extraction, verification, and report correction
from claim_extractor import extract_claims
from verifier import verify_claim, generate_corrected_report

# -------------------------------------------------------------
# 1. Initialize the Flask Application
# We configure the app, secret key, and local upload storage.
# -------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "evidencelock-hackathon-secret-key"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ACTIVE_CSV_PATH = os.path.join(UPLOAD_FOLDER, "active_dataset.csv")

# Only allow CSV file uploads
ALLOWED_EXTENSIONS = {"csv"}


# -------------------------------------------------------------
# 2. Helper Functions
# -------------------------------------------------------------
def allowed_file(filename):
    """Checks if the uploaded file has a .csv extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_active_dataframe():
    """
    Loads the active dataset. If a user previously uploaded a CSV,
    it loads that one. Otherwise, it defaults to samplesuperstore.csv.
    """
    if os.path.exists(ACTIVE_CSV_PATH):
        try:
            return pd.read_csv(ACTIVE_CSV_PATH), "Uploaded CSV (active)"
        except Exception:
            pass

    default_path = os.path.join(os.path.dirname(__file__), "samplesuperstore.csv")
    if os.path.exists(default_path):
        return pd.read_csv(default_path), "samplesuperstore.csv (default)"

    return None, "No dataset found"


def get_report_text():
    """Reads the default sample_report.txt file from disk."""
    report_file_path = os.path.join(os.path.dirname(__file__), "sample_report.txt")
    if os.path.exists(report_file_path):
        with open(report_file_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


# -------------------------------------------------------------
# 3. Route 1: Homepage & CSV Data Ingestion (Step 1)
# - Displays upload form and previews first 5 rows of data
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
            # Read CSV and cache locally for all downstream verification steps
            df = pd.read_csv(file)

            if df.empty:
                flash("The uploaded CSV file is empty. Please upload a dataset with data rows.", "warning")
                return redirect(request.url)

            df.to_csv(ACTIVE_CSV_PATH, index=False)

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
# - Scans report text and identifies checkable numeric claims
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
# - Connects extracted claims with real dataset calculations
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
# - Generates corrected report text with accurate calculations
# - Displays before/after side-by-side comparison
# - Displays accuracy rate and verdict breakdown charts
# -------------------------------------------------------------
@app.route("/results-dashboard", methods=["GET", "POST"])
def results_dashboard():
    df, dataset_name = get_active_dataframe()
    original_report_text = get_report_text()

    if request.method == "POST":
        custom_text = request.form.get("report_text", "").strip()
        if custom_text:
            original_report_text = custom_text

    # Extract claims and verify against data
    extracted_claims = extract_claims(original_report_text) if original_report_text else []
    verification_results = []
    if df is not None:
        for claim in extracted_claims:
            verification_results.append(verify_claim(claim, df))

    # Generate the corrected report using our verifier function
    corrected_report_text = generate_corrected_report(original_report_text, verification_results)

    # Compute metric counts
    total_claims = len(verification_results)
    correct_count = sum(1 for r in verification_results if r["verdict"] == "CORRECT")
    wrong_count = sum(1 for r in verification_results if r["verdict"] == "WRONG")
    unclear_count = sum(1 for r in verification_results if r["verdict"] == "UNCLEAR")

    # Accuracy Rate calculation: % of claims marked CORRECT out of evaluated claims (excluding UNCLEAR)
    evaluated_claims = correct_count + wrong_count
    if evaluated_claims > 0:
        accuracy_rate = round((correct_count / evaluated_claims) * 100, 1)
    else:
        accuracy_rate = 0.0

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
# 7. Route 5: Download Corrected Report as .txt file
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

    # Create downloadable text response
    return Response(
        corrected_report_text,
        mimetype="text/plain",
        headers={
            "Content-Disposition": "attachment;filename=corrected_business_report.txt",
            "Content-Type": "text/plain; charset=utf-8"
        }
    )


# -------------------------------------------------------------
# 8. Application Entry Point
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
