#!/usr/bin/env python3
"""
Octopus Energy Downloader - Streamlit Interactive Web Application
------------------------------------------------------------------
Run with:
    uv run streamlit run app.py
"""

import os
import json
from pathlib import Path
from datetime import datetime, date, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from octopus_downloader import OctopusDownloader, process_consumption_dataframe, load_config, save_config

st.set_page_config(
    page_title="Octopus Energy Data Downloader",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

CONFIG_PATH = Path("config.json")

# Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        color: #ff0055;
        font-weight: 700;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 25px;
    }
    .metric-box {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        border-left: 4px solid #ff0055;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<div class="main-header">⚡ Octopus Energy Data Downloader</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Download historical electricity and gas consumption data into CSV format with interactive visualizer</div>', unsafe_allow_html=True)

    config = load_config(CONFIG_PATH)

    # Sidebar - Credentials & Settings
    st.sidebar.header("🔑 API & Meter Credentials")
    
    saved_api_key = config.get("api_key", "")
    saved_acc = config.get("account_number", "")
    saved_mpan = config.get("mpan", "")
    saved_elec_serial = config.get("elec_serial", "")
    saved_mprn = config.get("mprn", "")
    saved_gas_serial = config.get("gas_serial", "")

    api_key = st.sidebar.text_input("Octopus API Key", value=saved_api_key, type="password", help="Found in your Octopus Energy account settings -> Developer API section.")
    account_number = st.sidebar.text_input("Account Number (Optional)", value=saved_acc, help="e.g. A-12345678. Used to auto-discover MPAN and MPRN details.")

    if account_number and api_key and st.sidebar.button("✨ Auto-Discover Meter Details"):
        downloader = OctopusDownloader(api_key=api_key)
        with st.spinner("Fetching account details from Octopus API..."):
            details = downloader.fetch_account_details(account_number)
            if details.get("electricity"):
                saved_mpan = details["electricity"][0]["mpan"]
                saved_elec_serial = details["electricity"][0]["serial_number"]
            if details.get("gas"):
                saved_mprn = details["gas"][0]["mprn"]
                saved_gas_serial = details["gas"][0]["serial_number"]
            
            st.sidebar.success("Meter details auto-discovered!")

    st.sidebar.subheader("⚡ Electricity Meter")
    mpan = st.sidebar.text_input("Electricity MPAN", value=saved_mpan)
    elec_serial = st.sidebar.text_input("Electricity Serial Number", value=saved_elec_serial)

    st.sidebar.subheader("🔥 Gas Meter")
    mprn = st.sidebar.text_input("Gas MPRN", value=saved_mprn)
    gas_serial = st.sidebar.text_input("Gas Serial Number", value=saved_gas_serial)

    save_creds = st.sidebar.checkbox("Save Credentials Locally (config.json)", value=True)

    if save_creds and (api_key or mpan or mprn):
        new_conf = {
            "api_key": api_key,
            "account_number": account_number,
            "mpan": mpan,
            "elec_serial": elec_serial,
            "mprn": mprn,
            "gas_serial": gas_serial
        }
        save_config(new_conf, CONFIG_PATH)

    # Main Area - Date Range & Parameters
    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        preset_range = st.selectbox(
            "📅 Date Range Preset",
            ["Last 30 Days", "Last 7 Days", "Last 90 Days", "Last 365 Days", "Custom Date Range"]
        )

    today = date.today()
    if preset_range == "Last 7 Days":
        start_date = today - timedelta(days=7)
        end_date = today
    elif preset_range == "Last 30 Days":
        start_date = today - timedelta(days=30)
        end_date = today
    elif preset_range == "Last 90 Days":
        start_date = today - timedelta(days=90)
        end_date = today
    elif preset_range == "Last 365 Days":
        start_date = today - timedelta(days=365)
        end_date = today
    else:
        start_date = today - timedelta(days=30)
        end_date = today

    with col2:
        if preset_range == "Custom Date Range":
            start_date = st.date_input("Start Date", value=start_date)
            end_date = st.date_input("End Date", value=end_date)
        else:
            st.info(f"Period: **{start_date}** to **{end_date}**")

    with col3:
        group_by = st.selectbox(
            "⏱️ Data Granularity",
            ["Half-Hourly (Raw)", "Hourly", "Daily", "Weekly", "Monthly"],
            index=0
        )

    fuel_selection = st.radio(
        "Select Energy Type to Download:",
        ["Both Electricity & Gas", "Electricity Only", "Gas Only"],
        horizontal=True
    )

    fetch_button = st.button("🚀 Download Consumption Data", type="primary", use_container_width=True)

    # Session State for holding dataframes
    if "df_elec" not in st.session_state:
        st.session_state.df_elec = None
    if "df_gas" not in st.session_state:
        st.session_state.df_gas = None

    if fetch_button:
        if not api_key:
            st.error("Please enter your Octopus Energy API Key in the sidebar.")
            return

        downloader = OctopusDownloader(api_key=api_key)
        
        group_param = group_by.lower().split()[0]
        if group_param in ("half-hourly", "raw"):
            group_param = None
        elif group_param == "hourly":
            group_param = "hour"
        elif group_param == "daily":
            group_param = "day"
        elif group_param == "weekly":
            group_param = "week"
        elif group_param == "monthly":
            group_param = "month"

        period_from_str = f"{start_date}T00:00:00Z"
        period_to_str = f"{end_date}T23:59:59Z"

        # Electricity
        if fuel_selection in ["Both Electricity & Gas", "Electricity Only"]:
            if mpan and elec_serial:
                with st.spinner("Fetching Electricity consumption..."):
                    elec_raw = downloader.fetch_consumption(
                        fuel="electricity",
                        point_id=mpan,
                        serial_number=elec_serial,
                        period_from=period_from_str,
                        period_to=period_to_str,
                        group_by=group_param
                    )
                    st.session_state.df_elec = process_consumption_dataframe(elec_raw, "electricity")
            else:
                st.warning("Skipped Electricity: MPAN or Meter Serial Number missing.")
                st.session_state.df_elec = None

        # Gas
        if fuel_selection in ["Both Electricity & Gas", "Gas Only"]:
            if mprn and gas_serial:
                with st.spinner("Fetching Gas consumption..."):
                    gas_raw = downloader.fetch_consumption(
                        fuel="gas",
                        point_id=mprn,
                        serial_number=gas_serial,
                        period_from=period_from_str,
                        period_to=period_to_str,
                        group_by=group_param
                    )
                    st.session_state.df_gas = process_consumption_dataframe(gas_raw, "gas")
            else:
                st.warning("Skipped Gas: MPRN or Meter Serial Number missing.")
                st.session_state.df_gas = None

    # Results Display
    df_elec = st.session_state.df_elec
    df_gas = st.session_state.df_gas

    if df_elec is not None or df_gas is not None:
        st.divider()
        st.subheader("📊 Consumption Analysis & CSV Downloads")

        tab_names = []
        if df_elec is not None and not df_elec.empty:
            tab_names.append("⚡ Electricity")
        if df_gas is not None and not df_gas.empty:
            tab_names.append("🔥 Gas")
        if df_elec is not None and not df_elec.empty and df_gas is not None and not df_gas.empty:
            tab_names.append("📈 Combined Comparison")

        if not tab_names:
            st.warning("No data was returned for the selected date range.")
            return

        tabs = st.tabs(tab_names)

        tab_idx = 0
        if df_elec is not None and not df_elec.empty:
            with tabs[tab_idx]:
                render_fuel_dashboard(df_elec, "Electricity", "kWh", "#00d2ff")
            tab_idx += 1

        if df_gas is not None and not df_gas.empty:
            with tabs[tab_idx]:
                render_fuel_dashboard(df_gas, "Gas", "m³ / kWh", "#ff5e62")
            tab_idx += 1

        if df_elec is not None and not df_elec.empty and df_gas is not None and not df_gas.empty:
            with tabs[tab_idx]:
                render_combined_dashboard(df_elec, df_gas)


def render_fuel_dashboard(df: pd.DataFrame, fuel_label: str, unit: str, color: str):
    total_val = df["consumption"].sum()
    avg_val = df["consumption"].mean()
    max_val = df["consumption"].max()
    record_count = len(df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Total {fuel_label}", f"{total_val:,.2f} {unit}")
    m2.metric("Average Reading", f"{avg_val:,.3f} {unit}")
    m3.metric("Peak Interval Usage", f"{max_val:,.3f} {unit}")
    m4.metric("Total Readings", f"{record_count:,}")

    # Plot
    fig = px.line(
        df,
        x="interval_start",
        y="consumption",
        title=f"{fuel_label} Usage Over Time ({unit})",
        labels={"interval_start": "Date & Time", "consumption": f"Usage ({unit})"},
        template="plotly_white"
    )
    fig.update_traces(line_color=color, fill='tozeroy')
    st.plotly_chart(fig, use_container_width=True)

    # CSV Download Button
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    filename = f"octopus_{fuel_label.lower()}_usage_{date.today()}.csv"

    st.download_button(
        label=f"📥 Download {fuel_label} CSV",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        type="primary"
    )

    # Preview Table
    with st.expander("🔍 View Raw Data Table"):
        st.dataframe(df, use_container_width=True)


def render_combined_dashboard(df_elec: pd.DataFrame, df_gas: pd.DataFrame):
    st.markdown("#### Electricity vs Gas Comparison")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_elec["interval_start"],
        y=df_elec["consumption"],
        mode='lines',
        name='Electricity (kWh)',
        line=dict(color='#00d2ff', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=df_gas["interval_start"],
        y=df_gas["consumption"],
        mode='lines',
        name='Gas (m³/kWh)',
        line=dict(color='#ff5e62', width=2)
    ))

    fig.update_layout(
        title="Combined Energy Consumption Time Series",
        xaxis_title="Date & Time",
        yaxis_title="Consumption",
        template="plotly_white"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Merge Dataframes on interval_start
    merged = pd.merge(
        df_elec[["interval_start", "interval_end", "date", "time_start", "consumption"]].rename(columns={"consumption": "electricity_consumption_kwh"}),
        df_gas[["interval_start", "consumption"]].rename(columns={"consumption": "gas_consumption_m3_kwh"}),
        on="interval_start",
        how="outer"
    ).sort_values("interval_start")

    csv_bytes = merged.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Merged Electricity & Gas CSV",
        data=csv_bytes,
        file_name=f"octopus_combined_energy_usage_{date.today()}.csv",
        mime="text/csv",
        type="primary"
    )

    with st.expander("🔍 View Combined Data Table"):
        st.dataframe(merged, use_container_width=True)


if __name__ == "__main__":
    main()
