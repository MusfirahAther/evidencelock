import os
import io
import uuid
import tempfile
import pandas as pd
from flask import Flask, render_template, request, flash, redirect, url_for, Response, session

# Import custom modules for claim extraction, verification, and report correction
from claim_extractor import extract_claims
from verifier import verify_claim, generate_corrected_report

# -------------------------------------------------------------
# 1. Base Paths & Flask App Configuration
# Explicitly anchor template and static paths for Vercel serverless.
# -------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DEFAULT_CSV_PATH = os.path.join(BASE_DIR, "samplesuperstore.csv")
DEFAULT_REPORT_PATH = os.path.join(BASE_DIR, "sample_report.txt")

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = "evidencelock-hackathon-secret-key"

ALLOWED_CSV_EXTENSIONS = {"csv"}
ALLOWED_TXT_EXTENSIONS = {"txt", "md"}

# In-memory session caches to support serverless stateless invocations
REPORT_CACHE = {}
DATASET_CACHE = {}

# Default fallback text for sample demo
FALLBACK_SAMPLE_REPORT = """QUARTERLY SALES PERFORMANCE REPORT
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
# 2. Session & State Management Helpers
# Handles custom user uploads and demo fallbacks across requests.
# -------------------------------------------------------------
def get_session_id():
    """Returns a unique session ID for the user session."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def allowed_csv(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_CSV_EXTENSIONS


def allowed_txt(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_TXT_EXTENSIONS


def get_default_sample_report():
    """Reads the default sample_report.txt file."""
    if os.path.exists(DEFAULT_REPORT_PATH):
        try:
            with open(DEFAULT_REPORT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return FALLBACK_SAMPLE_REPORT


def set_current_report(text, source_label="Custom Report"):
    """Saves the active report text in memory and session cache."""
    sid = get_session_id()
    REPORT_CACHE[sid] = text
    session["report_source"] = source_label
    try:
        report_tmp = os.path.join(tempfile.gettempdir(), f"report_{sid}.txt")
        with open(report_tmp, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def get_current_report():
    """
    Retrieves the currently active report text:
    1. Returns user's custom report (from textarea or uploaded .txt) if set.
    2. Falls back to sample_report.txt for demoing.
    """
    sid = get_session_id()
    if sid in REPORT_CACHE and REPORT_CACHE[sid]:
        return REPORT_CACHE[sid], session.get("report_source", "Custom Report")

    report_tmp = os.path.join(tempfile.gettempdir(), f"report_{sid}.txt")
    if os.path.exists(report_tmp):
        try:
            with open(report_tmp, "r", encoding="utf-8") as f:
                return f.read(), session.get("report_source", "Custom Report")
        except Exception:
            pass

    # Default to sample report
    sample_text = get_default_sample_report()
    return sample_text, "sample_report.txt (Sample Demo)"


def set_current_dataframe(df, filename="Uploaded CSV"):
    """Saves the active DataFrame in memory and /tmp cache."""
    sid = get_session_id()
    DATASET_CACHE[sid] = df
    session["dataset_name"] = filename
    try:
        csv_tmp = os.path.join(tempfile.gettempdir(), f"dataset_{sid}.csv")
        df.to_csv(csv_tmp, index=False)
    except Exception:
        pass


def get_current_dataframe():
    """
    Retrieves the active dataset:
    1. Returns user's uploaded custom CSV if present.
    2. Falls back to bundled samplesuperstore.csv.
    """
    sid = get_session_id()
    if sid in DATASET_CACHE and DATASET_CACHE[sid] is not None:
        return DATASET_CACHE[sid], session.get("dataset_name", "Uploaded CSV")

    csv_tmp = os.path.join(tempfile.gettempdir(), f"dataset_{sid}.csv")
    if os.path.exists(csv_tmp):
        try:
            return pd.read_csv(csv_tmp), session.get("dataset_name", "Uploaded CSV")
        except Exception:
            pass

    if os.path.exists(DEFAULT_CSV_PATH):
        try:
            return pd.read_csv(DEFAULT_CSV_PATH), "samplesuperstore.csv (Sample Default)"
        except Exception:
            pass

    return None, "No dataset available"


# -------------------------------------------------------------
# 3. Route 1: Homepage & CSV Data Ingestion (Step 1)
# -------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "csv_file" not in request.files:
            flash("No file part was found in the request. Please select a CSV file.", "error")
            return redirect(request.url)

        file = request.files["csv_file"]

        if file.filename == "":
            flash("No file selected. Please choose a CSV file to upload.", "error")
            return redirect(request.url)

        if not allowed_csv(file.filename):
            flash("Invalid file format. Please upload a CSV file (.csv only).", "error")
            return redirect(request.url)

        try:
            # Read CSV directly from memory stream
            file_bytes = file.read()
            df = pd.read_csv(io.BytesIO(file_bytes))

            if df.empty:
                flash("The uploaded CSV file is empty. Please upload a dataset with data rows.", "warning")
                return redirect(request.url)

            # Store as the active dataset for subsequent verification steps
            set_current_dataframe(df, file.filename)

            total_rows = len(df)
            total_columns = len(df.columns)
            column_names = df.columns.tolist()

            preview_df = df.head(5).fillna("")
            preview_rows = preview_df.values.tolist()

            flash(f"Successfully loaded {file.filename} ({total_rows:,} rows, {total_columns} columns)!", "success")

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

    # If visiting GET, check if an active dataset already exists in session
    df, dataset_name = get_current_dataframe()
    has_data = df is not None
    if has_data:
        total_rows = len(df)
        total_columns = len(df.columns)
        columns = df.columns.tolist()
        preview_rows = df.head(5).fillna("").values.tolist()
        return render_template(
            "index.html",
            filename=dataset_name,
            total_rows=total_rows,
            total_columns=total_columns,
            columns=columns,
            rows=preview_rows,
            has_data=True,
            active_page="data"
        )

    return render_template("index.html", has_data=False, active_page="data")


# -------------------------------------------------------------
# 4. Route 2: Claim Extraction Engine (Step 2)
# Supports:
# 1. Pasting custom report text in a textbox
# 2. Uploading a custom .txt report file
# 3. "Try a sample report" one-click button
# -------------------------------------------------------------
@app.route("/extract-claims", methods=["GET", "POST"])
def extract_claims_page():
    report_text, report_source = get_current_report()

    if request.method == "POST":
        action = request.form.get("action", "")

        # Option A: User clicked "Try Sample Report"
        if action == "load_sample":
            report_text = get_default_sample_report()
            report_source = "sample_report.txt (Sample Demo)"
            set_current_report(report_text, report_source)
            flash("Loaded sample quarterly sales report!", "info")

        # Option B: User uploaded a .txt report file
        elif "report_file" in request.files and request.files["report_file"].filename != "":
            file = request.files["report_file"]
            if allowed_txt(file.filename):
                try:
                    uploaded_content = file.read().decode("utf-8", errors="ignore").strip()
                    if uploaded_content:
                        report_text = uploaded_content
                        report_source = f"Uploaded File: {file.filename}"
                        set_current_report(report_text, report_source)
                        flash(f"Uploaded and extracted claims from {file.filename}!", "success")
                    else:
                        flash("The uploaded text file is empty.", "warning")
                except Exception as e:
                    flash(f"Error reading uploaded report file: {str(e)}", "error")
            else:
                flash("Invalid report file type. Please upload a .txt or .md file.", "error")

        # Option C: User pasted text in the textarea
        else:
            pasted_text = request.form.get("report_text", "").strip()
            if pasted_text:
                report_text = pasted_text
                report_source = "Custom Pasted Text"
                set_current_report(report_text, report_source)
                flash("Extracted claims from your pasted report text!", "success")

    # Extract claims from the currently active report
    claims = extract_claims(report_text) if report_text else []

    # Get active dataset name for header indicator
    _, dataset_name = get_current_dataframe()

    return render_template(
        "extract_claims.html",
        report_text=report_text,
        report_source=report_source,
        dataset_name=dataset_name,
        claims=claims,
        total_claims=len(claims),
        active_page="claims"
    )


# -------------------------------------------------------------
# 5. Route 3: Claim Verification Engine (Step 3)
# Verifies the active report claims against the active CSV dataset
# -------------------------------------------------------------
@app.route("/verify-claims", methods=["GET", "POST"])
def verify_claims_page():
    df, dataset_name = get_current_dataframe()
    report_text, report_source = get_current_report()

    if df is None:
        flash("No dataset loaded. Please upload a CSV first or use the sample dataset.", "warning")

    if not report_text:
        flash("No report loaded. Please paste or upload a report in Step 2.", "warning")

    # Extract claims from active report
    extracted_claims = extract_claims(report_text) if report_text else []

    # Verify each claim against active dataset
    verification_results = []
    if df is not None and extracted_claims:
        for claim in extracted_claims:
            res = verify_claim(claim, df)
            verification_results.append(res)
    elif extracted_claims:
        for claim in extracted_claims:
            verification_results.append({
                "original_sentence": claim.get("original_sentence", ""),
                "verdict": "UNCLEAR",
                "claimed_value": claim.get("claimed_value"),
                "real_value": None,
                "evidence": "No dataset available to perform ground-truth calculation."
            })

    correct_count = sum(1 for r in verification_results if r["verdict"] == "CORRECT")
    wrong_count = sum(1 for r in verification_results if r["verdict"] == "WRONG")
    unclear_count = sum(1 for r in verification_results if r["verdict"] == "UNCLEAR")

    return render_template(
        "verify_claims.html",
        results=verification_results,
        dataset_name=dataset_name,
        report_source=report_source,
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
    df, dataset_name = get_current_dataframe()
    report_text, report_source = get_current_report()

    # Extract and verify claims
    extracted_claims = extract_claims(report_text) if report_text else []
    verification_results = []
    if df is not None and extracted_claims:
        for claim in extracted_claims:
            verification_results.append(verify_claim(claim, df))

    # Generate the corrected version of THIS active report
    corrected_report_text = generate_corrected_report(report_text, verification_results)

    total_claims = len(verification_results)
    correct_count = sum(1 for r in verification_results if r["verdict"] == "CORRECT")
    wrong_count = sum(1 for r in verification_results if r["verdict"] == "WRONG")
    unclear_count = sum(1 for r in verification_results if r["verdict"] == "UNCLEAR")

    evaluated_claims = correct_count + wrong_count
    accuracy_rate = round((correct_count / evaluated_claims) * 100, 1) if evaluated_claims > 0 else 0.0

    return render_template(
        "results_dashboard.html",
        original_report_text=report_text,
        corrected_report_text=corrected_report_text,
        dataset_name=dataset_name,
        report_source=report_source,
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
# -------------------------------------------------------------
@app.route("/download-corrected-report")
def download_corrected_report():
    df, _ = get_current_dataframe()
    report_text, _ = get_current_report()

    extracted_claims = extract_claims(report_text) if report_text else []
    verification_results = []
    if df is not None and extracted_claims:
        for claim in extracted_claims:
            verification_results.append(verify_claim(claim, df))

    corrected_report_text = generate_corrected_report(report_text, verification_results)

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
