# 🚀 EvidenceLock — Vercel Deployment Guide & Architecture

This document explains the technical architecture and configuration used to deploy **EvidenceLock** (a Python Flask web app) onto **Vercel Serverless Functions**.

---

## 🏗️ Architectural Changes for Vercel Serverless

### 1. Serverless Entrypoint (`api/index.py`)
- **Why**: Vercel detects Python serverless lambdas in the `/api` directory.
- **How**: `api/index.py` dynamically adds the project root to `sys.path` and exposes the Flask WSGI `app` object so Vercel can route incoming HTTP requests into Flask.

### 2. Explicit Template & File Paths
- **Why**: In serverless runtimes, working directories can shift relative to the execution context (`/var/task`).
- **How**: `app.py` defines `BASE_DIR = os.path.abspath(os.path.dirname(__file__))` and binds `template_folder=os.path.join(BASE_DIR, "templates")`, guaranteeing that templates are always found.

### 3. In-Memory File Processing (Read-Only Filesystem Safe)
- **Why**: Vercel lambdas run in a read-only filesystem with ephemeral memory (except `/tmp`). Saving files directly to disk can fail.
- **How**:
  - Uploaded CSVs are read directly from memory streams using `io.BytesIO(file.read())` and Pandas `pd.read_csv()`.
  - Temporary session caches use `tempfile.gettempdir()` (`/tmp`) wrapped in exception guards.
  - The dataset seamlessly falls back to bundled [`samplesuperstore.csv`](samplesuperstore.csv).
  - The "Download Corrected Report" endpoint uses in-memory text streaming (`Response(..., mimetype="text/plain")`).

### 4. Vercel Configuration (`vercel.json`)
- Configures `@vercel/python` builder and rewrites all incoming routes `/(.*)` to `api/index.py`.

---

## 🌐 Step-by-Step Deployment Instructions on Vercel

1. **Log in to Vercel**:
   - Go to [https://vercel.com](https://vercel.com) and log in with your GitHub account.

2. **Add New Project**:
   - Click **"Add New..."** $\rightarrow$ **"Project"**.
   - Under **"Import Git Repository"**, find **`MusfirahAther/evidencelock`** and click **Import**.

3. **Configure Project**:
   - **Project Name**: `evidencelock` (or your preferred name).
   - **Framework Preset**: Leave as **Other** (Vercel automatically detects `vercel.json`).
   - **Root Directory**: `./` (leave default).
   - **Build & Development Settings**: Leave default.
   - **Environment Variables**: None required.

4. **Deploy**:
   - Click **"Deploy"**.
   - Vercel will install dependencies from `requirements.txt`, bundle `api/index.py`, and launch your live application with a public `*.vercel.app` URL!

---

## 🎯 Explaining this to Hackathon Judges

> *"We architected EvidenceLock as a stateless, serverless application deployed on Vercel. Because serverless runtimes feature immutable, read-only file systems, we designed our data ingestion and claim correction engines to process data entirely in-memory using byte streams and Pandas. This gives EvidenceLock sub-second cold starts, zero database maintenance overhead, and instant horizontal scalability."*
