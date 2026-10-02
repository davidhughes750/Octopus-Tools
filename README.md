# ⚡ Octopus Energy Usage Data Downloader (CSV Exporter)

A complete solution to download, analyze, and export your historical electricity and gas consumption data from Octopus Energy into CSV format.

---

## 🌟 Key Features

- **Electricity & Gas Support**: Fetches half-hourly raw reading data or aggregated totals for both fuel types.
- **Account Auto-Discovery**: Enter your Account Number (`A-XXXXXXXX`) and API Key to automatically discover your MPAN, MPRN, and meter serial numbers.
- **CSV Export**: Clean CSV outputs with ISO timestamps, human-readable date/time fields, fuel types, consumption values, and units.
- **Automatic Pagination**: Seamlessly fetches long date ranges spanning months or years across multiple API pages.
- **Flexible Interfaces**:
  1. **Python Command Line (CLI)**: Fast, scriptable, and headless.
  2. **Streamlit Interactive Web Dashboard**: Interactive time-series charts, metrics, and instant CSV downloads.
  3. **Standalone HTML/JS App (`index.html`)**: Zero-install web app that runs directly in your browser.

---

## 🚀 Getting Started

### Method 1: Using the Interactive Web App (Streamlit)

1. Open PowerShell / Command Prompt in this folder.
2. Run the application via `uv`:
   ```bash
   uv run streamlit run app.py
   ```
3. Open `http://localhost:8501` in your browser.
4. Enter your **Octopus API Key** in the left sidebar.
5. Click **Auto-Discover Meter Details** (or manually input your MPAN, MPRN, and Meter Serials).
6. Pick your date range and click **Download Consumption Data**.
7. Click **Download Electricity CSV** or **Download Gas CSV**.

---

### Method 2: Standalone Browser App (No Installation Needed)

1. Double-click `index.html` to open it in Chrome, Edge, or Firefox.
2. Enter your API Key and meter credentials (or click Auto-Detect).
3. Click **Fetch Usage Data & Generate CSVs**.
4. View interactive Chart.js graphs and click **Download CSV**!

---

### Method 3: Python Command Line (CLI)

#### Auto-Discover & Download Everything (Last 30 Days)
```bash
uv run python octopus_downloader.py --api-key YOUR_API_KEY --account-number A-12345678 --save-config
```

#### Download Specific Date Range
```bash
uv run python octopus_downloader.py --period-from 2024-01-01 --period-to 2024-12-31 --group-by day
```

#### CLI Parameters Overview
- `--api-key`: Octopus Developer API Key
- `--account-number`: Octopus Account Number (e.g. `A-12345678`)
- `--mpan`: Electricity MPAN
- `--elec-serial`: Electricity Meter Serial Number
- `--mprn`: Gas MPRN
- `--gas-serial`: Gas Meter Serial Number
- `--period-from`: ISO Date / Timestamp (e.g. `2024-01-01`)
- `--period-to`: ISO Date / Timestamp (e.g. `2024-12-31`)
- `--group-by`: Aggregation frequency (`half-hourly`, `hour`, `day`, `week`, `month`)
- `--fuel`: Fuel type (`both`, `electricity`, `gas`)
- `--output-dir`: Folder to save CSVs (default `./output`)
- `--save-config`: Save credentials locally to `config.json` for future calls

---

## 🔒 Security & Privacy

Your API Key and meter details are **never** uploaded anywhere. Requests go directly from your local machine to the official Octopus Energy API (`https://api.octopus.energy/v1`).
