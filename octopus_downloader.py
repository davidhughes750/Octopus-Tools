#!/usr/bin/env python3
"""
Octopus Energy Data Downloader
------------------------------
Downloads historical electricity and gas consumption data from Octopus Energy REST API
and exports to clean CSV files.

Supports:
- Electricity (MPAN + Meter Serial Number)
- Gas (MPRN + Meter Serial Number)
- Account Auto-Discovery (via Account Number)
- Custom Date Ranges & Granularity (Half-Hourly, Hourly, Daily, Weekly, Monthly)
- Config file persistence (config.json)
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser
import pandas as pd

API_BASE_URL = "https://api.octopus.energy/v1"


class OctopusDownloader:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.auth = (self.api_key, "")

    def fetch_account_details(self, account_number: str) -> dict:
        """Fetch account properties to discover MPANs, MPRNs, and meter serial numbers."""
        account_number = account_number.strip().upper()
        url = f"{API_BASE_URL}/accounts/{account_number}/"
        print(f"🔍 Fetching account details for {account_number}...")
        
        try:
            resp = requests.get(url, auth=self.auth, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"❌ Error fetching account details: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Status Code: {e.response.status_code}")
                print(f"   Response: {e.response.text}")
            return {}

        meters_info = {
            "electricity": [],
            "gas": []
        }

        properties = data.get("properties", [])
        for prop in properties:
            # Electricity Meter Points
            for ep in prop.get("electricity_meter_points", []):
                mpan = ep.get("mpan")
                for meter in ep.get("meters", []):
                    meters_info["electricity"].append({
                        "mpan": mpan,
                        "serial_number": meter.get("serial_number")
                    })
            # Gas Meter Points
            for gp in prop.get("gas_meter_points", []):
                mprn = gp.get("mprn")
                for meter in gp.get("meters", []):
                    meters_info["gas"].append({
                        "mprn": mprn,
                        "serial_number": meter.get("serial_number")
                    })

        return meters_info

    def fetch_consumption(
        self,
        fuel: str,
        point_id: str,
        serial_number: str,
        period_from: str = None,
        period_to: str = None,
        group_by: str = None,
        page_size: int = 25000
    ) -> list:
        """
        Fetch consumption data from Octopus API for electricity or gas.
        Handles pagination automatically until all records in period are fetched.
        """
        fuel = fuel.lower().strip()
        if fuel not in ("electricity", "gas"):
            raise ValueError("Fuel must be 'electricity' or 'gas'.")

        endpoint_type = "electricity-meter-points" if fuel == "electricity" else "gas-meter-points"
        url = f"{API_BASE_URL}/{endpoint_type}/{point_id}/meters/{serial_number}/consumption/"

        params = {
            "page_size": page_size,
            "order_by": "period"  # Chronological order
        }

        if period_from:
            params["period_from"] = format_iso_timestamp(period_from)
        if period_to:
            params["period_to"] = format_iso_timestamp(period_to)
        if group_by and group_by.lower() not in ("half-hourly", "raw"):
            params["group_by"] = group_by.lower()

        all_results = []
        page_count = 1

        print(f"📥 Fetching {fuel.capitalize()} consumption data (Point ID: {point_id}, Serial: {serial_number})...")

        current_url = url
        is_first_page = True

        while current_url:
            try:
                if is_first_page:
                    resp = requests.get(current_url, auth=self.auth, params=params, timeout=30)
                    is_first_page = False
                else:
                    # Subsequent pages already include query parameters in the 'next' URL
                    resp = requests.get(current_url, auth=self.auth, timeout=30)
                
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                all_results.extend(results)
                print(f"   Page {page_count}: Retrieved {len(results)} records (Total: {len(all_results)})")

                current_url = data.get("next")
                page_count += 1

            except requests.RequestException as e:
                print(f"❌ Error fetching {fuel} data: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"   Status Code: {e.response.status_code}")
                    print(f"   Response: {e.response.text}")
                break

        print(f"✅ Finished fetching {fuel.capitalize()} data. Total records: {len(all_results)}")
        return all_results


def format_iso_timestamp(date_str: str) -> str:
    """Format user date input into standard ISO 8601 string for Octopus API."""
    if not date_str:
        return None
    try:
        dt = date_parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception as e:
        raise ValueError(f"Invalid date format '{date_str}': {e}")


def process_consumption_dataframe(results: list, fuel_type: str) -> pd.DataFrame:
    """Convert raw API results into a clean, structured pandas DataFrame."""
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # Convert timestamps
    df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
    df["interval_end"] = pd.to_datetime(df["interval_end"], utc=True)

    # Ensure numerical consumption
    df["consumption"] = pd.to_numeric(df["consumption"], errors="coerce")

    # Sort chronologically
    df = df.sort_values(by="interval_start").reset_index(drop=True)

    # Formatting date strings for readability
    df["date"] = df["interval_start"].dt.strftime("%Y-%m-%d")
    df["time_start"] = df["interval_start"].dt.strftime("%H:%M:%S")
    df["time_end"] = df["interval_end"].dt.strftime("%H:%M:%S")
    df["day_of_week"] = df["interval_start"].dt.day_name()

    # Add fuel unit column
    # Octopus API: Electricity is kWh, Gas is m³ or kWh (typically m³ for smart meters)
    unit = "kWh" if fuel_type.lower() == "electricity" else "m³ (or kWh)"
    df["unit"] = unit
    df["fuel"] = fuel_type.capitalize()

    # Reorder columns
    cols = [
        "fuel",
        "interval_start",
        "interval_end",
        "date",
        "time_start",
        "time_end",
        "day_of_week",
        "consumption",
        "unit"
    ]
    existing_cols = [c for c in cols if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in cols]
    
    return df[existing_cols + remaining_cols]


def load_config(config_path: Path = Path("config.json")) -> dict:
    """Load configuration file if exists."""
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Warning: Could not read config file: {e}")
    return {}


def save_config(config_data: dict, config_path: Path = Path("config.json")):
    """Save configuration parameters locally."""
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        print(f"💾 Configuration saved to {config_path.resolve()}")
    except Exception as e:
        print(f"⚠️ Could not save config file: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Octopus Energy Usage Data Downloader (CSV Exporter)"
    )

    parser.add_argument("--api-key", help="Octopus Energy API Key (or set OCTOPUS_API_KEY env var)")
    parser.add_argument("--account-number", help="Octopus Account Number (e.g. A-12345678) to auto-discover meters")
    parser.add_argument("--mpan", help="Electricity MPAN")
    parser.add_argument("--elec-serial", help="Electricity Meter Serial Number")
    parser.add_argument("--mprn", help="Gas MPRN")
    parser.add_argument("--gas-serial", help="Gas Meter Serial Number")
    parser.add_argument("--period-from", help="Start date (e.g. 2024-01-01 or 2024-01-01T00:00:00Z)")
    parser.add_argument("--period-to", help="End date (e.g. 2024-12-31 or 2024-12-31T23:59:59Z)")
    parser.add_argument("--group-by", choices=["half-hourly", "hour", "day", "week", "month", "quarter"],
                        help="Grouping frequency (default: half-hourly raw data)")
    parser.add_argument("--fuel", choices=["both", "electricity", "gas"], default="both",
                        help="Fuel type to download (default: both)")
    parser.add_argument("--output-dir", default="./output", help="Directory where CSV files will be saved")
    parser.add_argument("--save-config", action="store_true", help="Save entered credentials to config.json")

    args = parser.parse_args()

    # Load from config file if available
    config = load_config()

    api_key = args.api_key or os.environ.get("OCTOPUS_API_KEY") or config.get("api_key")
    account_number = args.account_number or config.get("account_number")
    mpan = args.mpan or config.get("mpan")
    elec_serial = args.elec_serial or config.get("elec_serial")
    mprn = args.mprn or config.get("mprn")
    gas_serial = args.gas_serial or config.get("gas_serial")

    if not api_key:
        print("🔑 Octopus API Key is required.")
        api_key = input("Enter your Octopus API Key: ").strip()

    if not api_key:
        print("❌ Error: API key is mandatory. Exiting.")
        sys.exit(1)

    downloader = OctopusDownloader(api_key=api_key)

    # Attempt account auto-discovery if account number supplied
    if account_number and (not (mpan and elec_serial) or not (mprn and gas_serial)):
        discovered = downloader.fetch_account_details(account_number)
        if discovered.get("electricity"):
            if not mpan:
                mpan = discovered["electricity"][0].get("mpan")
            if not elec_serial:
                elec_serial = discovered["electricity"][0].get("serial_number")
            print(f"✨ Auto-discovered Electricity MPAN: {mpan}, Serial: {elec_serial}")
        
        if discovered.get("gas"):
            if not mprn:
                mprn = discovered["gas"][0].get("mprn")
            if not gas_serial:
                gas_serial = discovered["gas"][0].get("serial_number")
            print(f"✨ Auto-discovered Gas MPRN: {mprn}, Serial: {gas_serial}")

    # Prompt if missing
    fuel_choice = args.fuel.lower()

    if fuel_choice in ("both", "electricity") and not (mpan and elec_serial):
        print("\n⚡ Electricity Meter details required:")
        if not mpan:
            mpan = input("  Enter Electricity MPAN: ").strip()
        if not elec_serial:
            elec_serial = input("  Enter Electricity Meter Serial Number: ").strip()

    if fuel_choice in ("both", "gas") and not (mprn and gas_serial):
        print("\n🔥 Gas Meter details required:")
        if not mprn:
            mprn = input("  Enter Gas MPRN: ").strip()
        if not gas_serial:
            gas_serial = input("  Enter Gas Meter Serial Number: ").strip()

    # Save to config if requested
    if args.save_config:
        new_config = {
            "api_key": api_key,
            "account_number": account_number,
            "mpan": mpan,
            "elec_serial": elec_serial,
            "mprn": mprn,
            "gas_serial": gas_serial
        }
        save_config(new_config)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Process Electricity
    if fuel_choice in ("both", "electricity") and mpan and elec_serial:
        elec_results = downloader.fetch_consumption(
            fuel="electricity",
            point_id=mpan,
            serial_number=elec_serial,
            period_from=args.period_from,
            period_to=args.period_to,
            group_by=args.group_by
        )
        if elec_results:
            df_elec = process_consumption_dataframe(elec_results, "electricity")
            elec_file = output_dir / f"electricity_consumption_{timestamp_str}.csv"
            df_elec.to_csv(elec_file, index=False)
            total_kwh = df_elec["consumption"].sum()
            print(f"🎉 Electricity CSV saved to: {elec_file.resolve()}")
            print(f"   📊 Total Electricity Consumption: {total_kwh:.2f} kWh across {len(df_elec)} readings.")

    # Process Gas
    if fuel_choice in ("both", "gas") and mprn and gas_serial:
        gas_results = downloader.fetch_consumption(
            fuel="gas",
            point_id=mprn,
            serial_number=gas_serial,
            period_from=args.period_from,
            period_to=args.period_to,
            group_by=args.group_by
        )
        if gas_results:
            df_gas = process_consumption_dataframe(gas_results, "gas")
            gas_file = output_dir / f"gas_consumption_{timestamp_str}.csv"
            df_gas.to_csv(gas_file, index=False)
            total_gas = df_gas["consumption"].sum()
            print(f"🎉 Gas CSV saved to: {gas_file.resolve()}")
            print(f"   📊 Total Gas Consumption: {total_gas:.2f} m³/kWh across {len(df_gas)} readings.")

    print("\n✨ All operations completed successfully!")


if __name__ == "__main__":
    main()
