# ERP Copilot — Intelligent ERP Assistant (Prototype)

Option 2 exercise submission: an AI-powered ERP feature that helps users make
faster, better decisions using real-time system data.

## What it does
Reads three live ERP-style tables — **Purchase Orders**, **Inventory**, and
**Vendors** — from Google Sheets, computes risk signals (overdue POs,
stockout risk, underperforming vendors), ranks them by severity, and uses
Claude to turn that ranked list into a short, plain-language, prioritized
briefing. Users can also ask free-form questions ("Which vendors are causing
the most delays this month?") and get answers grounded only in the live data.

## 1. Set up the Google Sheet (public dataset)
1. Create a new Google Sheet with three tabs named `Purchase_Orders`,
   `Inventory`, and `Vendors`.
2. Import the matching CSV from `data/` into each tab
   (File → Import → Upload → Insert as new sheet).
3. For each tab: **File → Share → Publish to web** → select the tab →
   format **CSV** → Publish. Copy the resulting URL.
4. Also set sharing to **Anyone with the link → Viewer** so the sheet itself
   can be submitted as your public dataset link.
5. Paste the three published CSV URLs into the app's sidebar.

Published Links:
Purchased Order: https://docs.google.com/spreadsheets/d/e/2PACX-1vQz5f272npS7Kt_E70WobjWirTSZavZEWOx2HW4njYbud23vKzg6H7imv_Ygmhq9iDY96CMQaeAy13G/pub?gid=1893128557&single=true&output=csv
Inventory: https://docs.google.com/spreadsheets/d/e/2PACX-1vQz5f272npS7Kt_E70WobjWirTSZavZEWOx2HW4njYbud23vKzg6H7imv_Ygmhq9iDY96CMQaeAy13G/pub?gid=1103151139&single=true&output=csv
Vendors: https://docs.google.com/spreadsheets/d/e/2PACX-1vQz5f272npS7Kt_E70WobjWirTSZavZEWOx2HW4njYbud23vKzg6H7imv_Ygmhq9iDY96CMQaeAy13G/pub?gid=1205952954&single=true&output=csv

(The bundled CSVs in `data/` are synthetic and safe to publish — no real
company data.)

## 2. Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Open the sidebar and add your Anthropic API key to enable the AI briefing
and chat (the dashboard and risk tables work without one).

## 3. Deploy for a public prototype link
Push this folder to a public GitHub repo, then on
[share.streamlit.io](https://share.streamlit.io):
1. "New app" → pick the repo → main file `app.py` → Deploy.
2. In app settings → **Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
3. Share the generated `*.streamlit.app` URL as your prototype link.

## Files
```
app.py                    Streamlit app (dashboard + AI briefing + chat)
requirements.txt          Python dependencies
data/purchase_orders.csv  Sample PO data
data/inventory.csv        Sample inventory data
data/vendors.csv          Sample vendor performance data
design_doc.docx           Design document
summary.md                100-word summary
```
