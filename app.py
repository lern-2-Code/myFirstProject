import streamlit as st
import pandas as pd
import plotly.express as px
import os
import json
import io
from datetime import datetime, timedelta

# Configuration and File Setup
DB_FILE = "budget_data.csv"
SETTINGS_FILE = "settings.json"

BUDGET_CATEGORIES = ["Utilities", "Car", "Food", "Home", "Education", "Social", "Personal"]
ALL_CATEGORIES = BUDGET_CATEGORIES + ["Salary", "Other"]

# ----------------- DATA CORE FUNCTIONS -----------------
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    return pd.DataFrame(columns=["Date", "Type", "Category", "Amount", "Description"])

def save_data(df):
    df.to_csv(DB_FILE, index=False)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {"start_date": datetime.today().strftime("%Y-%m-%d"), "amount": 0.0, "budgets": {cat: 0.0 for cat in BUDGET_CATEGORIES}}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def process_recurring_salary(df):
    settings = load_settings()
    if not settings or settings.get("amount", 0) <= 0:
        return df, False
    
    start_date = datetime.strptime(settings["start_date"], "%Y-%m-%d")
    amount = settings["amount"]
    today = datetime.combine(datetime.today().date(), datetime.min.time())
    
    pay_dates = []
    current_pay_date = start_date
    while current_pay_date <= today:
        pay_dates.append(current_pay_date)
        current_pay_date += timedelta(days=14)
        
    new_entries = []
    existing_salary_dates = []
    
    if not df.empty:
        salary_df = df[(df["Type"] == "Income") & (df["Category"] == "Salary") & (df["Description"] == "Automated Biweekly Pay")]
        existing_salary_dates = pd.to_datetime(salary_df["Date"]).dt.normalize().tolist()

    for p_date in pay_dates:
        if pd.Timestamp(p_date) not in [pd.Timestamp(d) for d in existing_salary_dates]:
            new_entries.append({
                "Date": p_date,
                "Type": "Income",
                "Category": "Salary",
                "Amount": amount,
                "Description": "Automated Biweekly Pay"
            })
            
    if new_entries:
        df = pd.concat([df, pd.DataFrame(new_entries)], ignore_index=True)
        save_data(df)
        return df, True
        
    return df, False

def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
    return output.getvalue()

# ----------------- APP CONFIGURATION & SECURITY GATE -----------------
st.set_page_config(page_title="Personal Budget Tracker", page_icon="💰", layout="wide")

def check_password():
    """Returns True if the user has authenticated successfully."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Render landing screen for locked portal
    st.title("🔒 Secure Budget Portal")
    user_password = st.text_input("Enter Access Password", type="password")
    
    if st.button("Unlock Dashboard"):
        # 🟢 LOCAL TESTING PASSWORD (or use st.secrets["PASSWORD"] for safe deployments)
        if user_password == st.secrets["PASSWORD"]:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("❌ Invalid password. Access Denied.")
            
    return False

# Strict stop if user has not cleared the portal security line
if not check_password():
    st.stop()

# =========================================================================
# 🔓 SECURE WORKSPACE AREA (Runs strictly *after* authentication verification)
# =========================================================================
st.title("💰 Personal Budget Tracker")

df = load_data()
df, updated = process_recurring_salary(df)
if updated:
    st.toast("🔄 Biweekly paycheck allocations updated!", icon="🏦")

current_settings = load_settings()
saved_budgets = current_settings.get("budgets", {cat: 0.0 for cat in BUDGET_CATEGORIES})

# Dashboard Container Tabs (Built safely post-login)
tab_tracker, tab_analytics, tab_setup = st.tabs(["📊 Tracker & Reports", "📈 Interactive Analytics", "⚙️ System Setup"])

# ----------------- SIDEBAR CONTAINER: MANUAL ADD -----------------
st.sidebar.header("Add Entry")
with st.sidebar.form("entry_form", clear_on_submit=True):
    date = st.date_input("Date", datetime.today())
    entry_type = st.selectbox("Type", ["Expense", "Income"])
    category = st.selectbox("Category", ALL_CATEGORIES)
    amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
    description = st.text_input("Description/Notes")
    
    submit = st.form_submit_button("Add Entry")
    
    if submit:
        new_row = pd.DataFrame([{"Date": pd.to_datetime(date), "Type": entry_type, "Category": category, "Amount": amount, "Description": description}])
        df = pd.concat([df, new_row], ignore_index=True)
        save_data(df)
        st.sidebar.success("Entry added!")
        st.rerun()

# ----------------- TAB 1: TRACKER & REPORTS VIEW -----------------
with tab_tracker:
    if df.empty:
        st.info("No data available yet. Please add data using the sidebar form or system setup panel.")
    else:
        # Macro Core Balance Metrics
        total_income = df[df["Type"] == "Income"]["Amount"].sum()
        total_expense = df[df["Type"] == "Expense"]["Amount"].sum()
        net_balance = total_income - total_expense

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Income", f"${total_income:,.2f}")
        col2.metric("Total Expenses", f"${total_expense:,.2f}", delta_color="inverse")
        col3.metric("Net Balance", f"${net_balance:,.2f}")

        st.markdown("---")
        st.subheader("🎯 Biweekly Budget Goals vs Actual Spending")
        
        start_pay = datetime.strptime(current_settings["start_date"], "%Y-%m-%d")
        days_since = (datetime.today() - start_pay).days
        current_cycle_start = start_pay + timedelta(days=(days_since // 14) * 14)
        
        st.caption(f"Showing expenses tracked during your current biweekly period: **{current_cycle_start.strftime('%Y-%m-%d')}** to **{(current_cycle_start + timedelta(days=13)).strftime('%Y-%m-%d')}**")
        
        cycle_df = df[(df["Type"] == "Expense") & (df["Date"] >= pd.Timestamp(current_cycle_start))]
        
        # Aggregate any broken metric rules to display a unified tracking header warning
        overages = []
        for cat in BUDGET_CATEGORIES:
            spent = cycle_df[cycle_df["Category"] == cat]["Amount"].sum()
            cap = saved_budgets.get(cat, 0.0)
            if cap > 0 and spent > cap:
                overages.append(f"**{cat}** (Over by ${spent - cap:,.2f})")
        
        if overages:
            st.error(f"🚨 **Budget Alert!** You have exceeded your biweekly allowance limit in: {', '.join(overages)}")

        # Construct Progress Grid
        prog_cols = st.columns(len(BUDGET_CATEGORIES))
        for idx, cat in enumerate(BUDGET_CATEGORIES):
            with prog_cols[idx]:
                cat_spent = cycle_df[cycle_df["Category"] == cat]["Amount"].sum()
                cat_cap = saved_budgets.get(cat, 0.0)
                
                st.markdown(f"**{cat}**")
                st.markdown(f"${cat_spent:,.2f} / ${cat_cap:,.2f}")
                
                if cat_cap > 0:
                    ratio = min(cat_spent / cat_cap, 1.0)
                    st.progress(ratio)
                else:
                    st.caption("No cap set")

        st.markdown("---")
        st.subheader("📋 Transaction History Ledger")
        
        # Search & Document Processing Grid
        hist_col1, hist_col2 = st.columns(2)
        with hist_col1:
            filter_type = st.selectbox("Filter History Table", ["All", "Income", "Expense"])
            filtered_df = df if filter_type == "All" else df[df["Type"] == filter_type]
        with hist_col2:
            st.markdown("<br>", unsafe_allow_html=True) # Structural break fix line
            excel_data = convert_df_to_excel(df)
            st.download_button(
                label="📥 Export Ledger to Excel",
                data=excel_data,
                file_name=f"budget_report_{datetime.today().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        st.dataframe(filtered_df.sort_values(by="Date", ascending=False), use_container_width=True)

        if st.button("⚠️ Clear Transaction History Ledger"):
            if os.path.exists(DB_FILE):
                os.remove(DB_FILE)
            st.success("History wiped!")
            st.rerun()

# ----------------- TAB 2: INTERACTIVE ANALYTICS VIEW -----------------
with tab_analytics:
    st.subheader("📈 Financial Intelligence & Performance Deep-Dive")
    
    if df.empty:
        st.info("Analytics engine is waiting for transaction data records.")
    else:
        st.write("#### 🔍 Filter Analysis Window")
        min_date = df["Date"].min().to_pydatetime()
        max_date = df["Date"].max().to_pydatetime()
        
        if min_date == max_date:
            min_date = min_date - timedelta(days=1)

        slider_col1, slider_col2 = st.columns(2)
        with slider_col1:
            selected_range = st.slider("Select Window Range", min_value=min_date, max_value=max_date, value=(min_date, max_date), format="YYYY-MM-DD")
        with slider_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption(f"Analyzing data from **{selected_range[0].strftime('%Y-%m-%d')}** to **{selected_range[1].strftime('%Y-%m-%d')}**")

