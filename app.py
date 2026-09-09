"""
ERP Copilot — Intelligent Procure-to-Pay Assistant
----------------------------------------------------
A prototype AI-powered ERP feature that turns live procurement, inventory,
and vendor data (served from Google Sheets) into prioritized, plain-language
decisions for a procurement/operations user.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

Data source:
    Reads three "tables" (Purchase_Orders, Inventory, Vendors) from Google
    Sheets, published as CSV. Paste your published CSV URLs in the sidebar,
    or point the app at the bundled sample CSVs in ./data for an offline demo.

AI layer:
    Uses the Anthropic API (Claude) to turn the computed risk signals into a
    natural-language, prioritized briefing and to answer free-form questions.
    An Anthropic API key is required only for the AI narrative — all risk
    scoring/flagging works without one, so the dashboard is still useful
    offline.
"""

import io
import os
from datetime import datetime, date

import pandas as pd
import requests
import streamlit as st

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="ERP Copilot — Procure-to-Pay Assistant",
    page_icon="🧭",
    layout="wide",
)

TODAY = date.today()

DEFAULT_PO_CSV = "data/purchase_orders.csv"
DEFAULT_INV_CSV = "data/inventory.csv"
DEFAULT_VEN_CSV = "data/vendors.csv"

# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def _to_gsheet_csv_url(url_or_id: str) -> str:
    """Accept a full published-CSV link, a normal Sheets share link, or a
    bare sheet ID, and return a URL pandas can read directly."""
    if not url_or_id:
        return url_or_id
    url_or_id = url_or_id.strip()
    if "docs.google.com" in url_or_id:
        if "/export?format=csv" in url_or_id or "output=csv" in url_or_id:
            return url_or_id
        # Turn a normal /edit link into an export=csv link
        if "/edit" in url_or_id:
            base = url_or_id.split("/edit")[0]
            return base + "/export?format=csv"
        return url_or_id
    # Assume it's a bare Sheet ID
    return f"https://docs.google.com/spreadsheets/d/{url_or_id}/export?format=csv"


@st.cache_data(ttl=300, show_spinner=False)
def load_table(source: str, fallback_path: str) -> pd.DataFrame:
    """Load a table from a Google Sheets CSV URL, falling back to the
    bundled sample CSV if no URL is given or the fetch fails."""
    if source:
        try:
            url = _to_gsheet_csv_url(source)
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return pd.read_csv(io.StringIO(resp.text))
        except Exception as exc:  # noqa: BLE001
            st.sidebar.warning(f"Could not load from Sheets ({exc}); using sample data.")
    return pd.read_csv(fallback_path)


# --------------------------------------------------------------------------
# Sidebar — data source + AI config
# --------------------------------------------------------------------------
st.sidebar.header("⚙️ Data sources")
st.sidebar.caption(
    "Paste published-CSV links from your Google Sheet (File → Share → "
    "Publish to web → CSV), one per table. Leave blank to use bundled sample data."
)
po_source = st.sidebar.text_input("Purchase Orders sheet URL", value="")
inv_source = st.sidebar.text_input("Inventory sheet URL", value="")
ven_source = st.sidebar.text_input("Vendors sheet URL", value="")

if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()

st.sidebar.header("🤖 AI assistant")
api_key = st.sidebar.text_input(
    "Anthropic API key", value=os.environ.get("ANTHROPIC_API_KEY", ""), type="password"
)
st.sidebar.caption(
    "Optional. Without a key the dashboard still shows every computed risk "
    "signal — you just won't get the AI-written briefing or chat answers."
)

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
po_df = load_table(po_source, DEFAULT_PO_CSV)
inv_df = load_table(inv_source, DEFAULT_INV_CSV)
ven_df = load_table(ven_source, DEFAULT_VEN_CSV)

po_df["Expected_Delivery"] = pd.to_datetime(po_df["Expected_Delivery"]).dt.date
po_df["Order_Date"] = pd.to_datetime(po_df["Order_Date"]).dt.date

# --------------------------------------------------------------------------
# Risk / signal computation (the "reasoning over live data" layer)
# --------------------------------------------------------------------------
def compute_po_risk(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Days_Overdue"] = df.apply(
        lambda r: max((TODAY - r["Expected_Delivery"]).days, 0)
        if r["Status"] not in ("Delivered", "Closed")
        else 0,
        axis=1,
    )
    df["Is_Overdue"] = (df["Status"] == "Overdue") | (df["Days_Overdue"] > 0)
    return df


def compute_inventory_risk(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Days_Of_Cover"] = (df["Current_Stock"] / df["Avg_Daily_Usage"]).round(1)
    df["Below_Reorder_Point"] = df["Current_Stock"] <= df["Reorder_Point"]
    df["Stockout_Risk"] = df["Days_Of_Cover"] < df["Lead_Time_Days"]
    return df


def compute_vendor_risk(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Flagged"] = (df["Risk_Rating"] == "High") | (df["On_Time_Delivery_Rate_Pct"] < 75)
    return df


po_risk = compute_po_risk(po_df)
inv_risk = compute_inventory_risk(inv_df)
ven_risk = compute_vendor_risk(ven_df)


def build_priority_actions(po_risk, inv_risk, ven_risk) -> pd.DataFrame:
    """Merge signals from all three tables into one ranked action list —
    this is the core "decision assistant" logic."""
    actions = []

    for _, r in po_risk[po_risk["Is_Overdue"]].iterrows():
        severity = min(10, 4 + r["Days_Overdue"] // 3)
        actions.append({
            "Severity": severity,
            "Area": "Purchase Order",
            "Reference": r["PO_ID"],
            "Issue": f"{r['Item']} from {r['Vendor']} is {r['Days_Overdue']} day(s) overdue "
                     f"(expected {r['Expected_Delivery']}).",
            "Recommended Action": f"Escalate {r['PO_ID']} with {r['Vendor']}; "
                                   f"confirm new ETA and assess line-stop risk.",
        })

    for _, r in inv_risk[inv_risk["Stockout_Risk"]].iterrows():
        severity = 9 if r["Days_Of_Cover"] < r["Lead_Time_Days"] / 2 else 6
        actions.append({
            "Severity": severity,
            "Area": "Inventory",
            "Reference": r["Item"],
            "Issue": f"{r['Item']} has {r['Days_Of_Cover']} days of stock cover but a "
                     f"{r['Lead_Time_Days']}-day vendor lead time (stockout risk).",
            "Recommended Action": f"Raise an expedited PO for {r['Item']} now; "
                                   f"current stock {r['Current_Stock']} vs reorder point {r['Reorder_Point']}.",
        })

    for _, r in ven_risk[ven_risk["Flagged"]].iterrows():
        severity = 7 if r["Risk_Rating"] == "High" else 5
        actions.append({
            "Severity": severity,
            "Area": "Vendor",
            "Reference": r["Vendor"],
            "Issue": f"{r['Vendor']} on-time delivery is {r['On_Time_Delivery_Rate_Pct']}% "
                     f"(avg delay {r['Avg_Delay_Days']} days, risk rating {r['Risk_Rating']}).",
            "Recommended Action": f"Review sourcing for {r['Vendor']}'s open POs; "
                                   f"consider a secondary vendor for critical items.",
        })

    if not actions:
        return pd.DataFrame(columns=["Severity", "Area", "Reference", "Issue", "Recommended Action"])
    return pd.DataFrame(actions).sort_values("Severity", ascending=False).reset_index(drop=True)


priority_df = build_priority_actions(po_risk, inv_risk, ven_risk)

# --------------------------------------------------------------------------
# Header + KPIs
# --------------------------------------------------------------------------
st.title("🧭 ERP Copilot — Procure-to-Pay Assistant")
st.caption(
    "Option 2: Intelligent ERP Assistant — turns live purchase order, "
    "inventory, and vendor data into prioritized, plain-language decisions."
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Overdue POs", int(po_risk["Is_Overdue"].sum()))
k2.metric("Items at stockout risk", int(inv_risk["Stockout_Risk"].sum()))
k3.metric("High/flagged-risk vendors", int(ven_risk["Flagged"].sum()))
k4.metric("Open PO value (USD)", f"{po_risk.loc[po_risk['Status'] != 'Closed', 'Amount_USD'].sum():,.0f}")

st.divider()

# --------------------------------------------------------------------------
# AI briefing
# --------------------------------------------------------------------------
st.subheader("📋 AI priority briefing")

def call_claude(system_prompt: str, user_prompt: str, api_key: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


SYSTEM_PROMPT = (
    "You are an ERP procure-to-pay copilot for an operations/procurement "
    "manager. You are given a table of already-computed risk signals "
    "(overdue purchase orders, at-risk inventory items, and flagged "
    "vendors). Write a short, prioritized briefing: 3-6 bullet points, "
    "most severe first, each with the concrete recommended action. Base "
    "every statement strictly on the data given — never invent figures, "
    "vendors, or items not present in it. Be concise and business-toned."
)

briefing_col, chat_col = st.columns([1, 1])

with briefing_col:
    if st.button("Generate today's briefing", type="primary"):
        if priority_df.empty:
            st.info("No risk signals detected in the current data — nothing to escalate today.")
        elif not api_key:
            st.warning("Add an Anthropic API key in the sidebar to generate the AI-written briefing.")
            st.dataframe(priority_df, use_container_width=True, hide_index=True)
        else:
            with st.spinner("Thinking..."):
                data_context = priority_df.to_csv(index=False)
                try:
                    briefing = call_claude(
                        SYSTEM_PROMPT,
                        f"Risk signals as of {TODAY}:\n{data_context}\n\nWrite the briefing.",
                        api_key,
                    )
                    st.markdown(briefing)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"AI call failed: {exc}")

    with st.expander("View all computed risk signals (ranked)"):
        st.dataframe(priority_df, use_container_width=True, hide_index=True)

with chat_col:
    st.markdown("**Ask the assistant a question**")
    question = st.text_input(
        "e.g. Which vendors are causing the most delays this month?",
        key="qbox",
    )
    if st.button("Ask"):
        if not api_key:
            st.warning("Add an Anthropic API key in the sidebar to ask questions.")
        else:
            with st.spinner("Thinking..."):
                context = (
                    "PURCHASE ORDERS:\n" + po_risk.to_csv(index=False) +
                    "\nINVENTORY:\n" + inv_risk.to_csv(index=False) +
                    "\nVENDORS:\n" + ven_risk.to_csv(index=False)
                )
                try:
                    answer = call_claude(
                        SYSTEM_PROMPT,
                        f"Data as of {TODAY}:\n{context}\n\nQuestion: {question}\n"
                        "Answer using only this data; say so if it isn't answerable from it.",
                        api_key,
                    )
                    st.markdown(answer)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"AI call failed: {exc}")

st.divider()

# --------------------------------------------------------------------------
# Underlying tables
# --------------------------------------------------------------------------
t1, t2, t3 = st.tabs(["Purchase Orders", "Inventory", "Vendors"])

with t1:
    st.dataframe(
        po_risk.style.apply(
            lambda row: ["background-color:#ffe3e3" if row["Is_Overdue"] else "" for _ in row],
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )

with t2:
    st.dataframe(
        inv_risk.style.apply(
            lambda row: ["background-color:#ffe3e3" if row["Stockout_Risk"] else "" for _ in row],
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )

with t3:
    st.dataframe(
        ven_risk.style.apply(
            lambda row: ["background-color:#ffe3e3" if row["Flagged"] else "" for _ in row],
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    "Prototype for the Intelligent ERP Assistant exercise. Sample data is "
    "synthetic and for demonstration only."
)
