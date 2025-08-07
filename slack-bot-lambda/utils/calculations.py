"""
P&L calculations module - exactly matching WeeklyDeskPnL/calculations.py
"""
import pandas as pd
from datetime import timedelta
import os

def run_calculations(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Run P&L calculations exactly like WeeklyDeskPnL/calculations.py
    
    Args:
        cutoff_date (pd.Timestamp): Cutoff date for calculations
        csv_file_path (str): Path to the CSV export file
        
    Returns:
        dict: Metrics dictionary matching WeeklyDeskPnL format
    """
    try:
        # Load and Clean Data (exactly like calculations.py)
        df = pd.read_csv(csv_file_path)
        df.columns = df.columns.str.strip()
        df = df[df["Order ID"] != 6315.0]  # Exclude specific order as in original
        df.rename(columns={"Revenue Received from Counterparty (USD)": "Volume (USD)"}, inplace=True)
        
        # Clean numeric columns
        df["Total P&L (USD)"] = pd.to_numeric(
            df["Total P&L (USD)"].astype(str).str.replace(",", "").str.strip().replace("", "0"),
            errors="coerce"
        )
        
        df["Volume (USD)"] = pd.to_numeric(
            df["Volume (USD)"].astype(str).str.replace(",", "").str.strip().replace("", "0"),
            errors="coerce"
        )
        
        df["Booking Date"] = pd.to_datetime(df["Booking Date"], errors="coerce")
        df.dropna(subset=["Booking Date"], inplace=True)
        df = df[df["Booking Date"] <= cutoff_date]
        
        # Add Ratio
        df["Volume/P&L Ratio"] = df["Volume (USD)"] / df["Total P&L (USD)"]
        
        # Period Buckets
        df["Year"] = df["Booking Date"].dt.year
        df["Month"] = df["Booking Date"].dt.month
        
        current_year = cutoff_date.year
        current_month = cutoff_date.month
        
        df_ytd = df[df["Year"] == current_year]
        df_mtd = df_ytd[df_ytd["Month"] == current_month]
        
        # YTD / MTD Metrics
        ytd_pnl = df_ytd["Total P&L (USD)"].sum()
        ytd_volume = df_ytd["Volume (USD)"].sum()
        mtd_pnl = df_mtd["Total P&L (USD)"].sum()
        mtd_volume = df_mtd["Volume (USD)"].sum()
        
        print(f"YTD P&L: {ytd_pnl:,.2f}")
        print(f"YTD Volume: {ytd_volume:,.2f}")
        print(f"MTD P&L: {mtd_pnl:,.2f}")
        print(f"MTD Volume: {mtd_volume:,.2f}")
        
        ytd_margin = ytd_pnl / ytd_volume if ytd_volume else None
        print(f"YTD Margin: {ytd_margin:.2%}" if ytd_margin is not None else "YTD Margin: N/A")
        
        start_of_year = pd.to_datetime(f"{current_year}-01-01")
        days_elapsed = (cutoff_date - start_of_year).days + 1
        annualized_pnl = (ytd_pnl / days_elapsed) * 365 if days_elapsed > 0 else None
        print(f"Annualized P&L Run-Rate: {annualized_pnl:,.2f}" if annualized_pnl is not None else "Annualized P&L Run-Rate: N/A")
        
        # Weekly Metrics (Last 7 Days)
        start_of_week = cutoff_date - timedelta(days=6)
        df_last_week = df[(df["Booking Date"] >= start_of_week) & (df["Booking Date"] <= cutoff_date)]
        
        last_week_pnl = df_last_week["Total P&L (USD)"].sum()
        last_week_volume = df_last_week["Volume (USD)"].sum()
        weekly_margin = last_week_pnl / last_week_volume if last_week_volume else None
        
        print(f"\nWeekly P&L ({start_of_week.date()} to {cutoff_date.date()}): {last_week_pnl:,.2f}")
        print(f"Weekly Volume: {last_week_volume:,.2f}")
        print(f"Weekly Margin: {weekly_margin:.2%}" if weekly_margin is not None else "Weekly Margin: N/A")
        
        # WoW % Change
        prev_week_start = cutoff_date - timedelta(days=13)
        prev_week_end = cutoff_date - timedelta(days=7)
        df_prev_week = df[(df["Booking Date"] >= prev_week_start) & (df["Booking Date"] <= prev_week_end)]
        
        prev_pnl = df_prev_week["Total P&L (USD)"].sum()
        prev_volume = df_prev_week["Volume (USD)"].sum()
        
        def pct_change(current, prev):
            if prev == 0:
                return None if current == 0 else float('inf')
            return (current - prev) / prev * 100
        
        pnl_change = pct_change(last_week_pnl, prev_pnl)
        volume_change = pct_change(last_week_volume, prev_volume)
        
        print(f"\nWoW P&L Change: {pnl_change:.2f}%" if pnl_change is not None else "WoW P&L Change: N/A")
        print(f"WoW Volume Change: {volume_change:.2f}%" if volume_change is not None else "WoW Volume Change: N/A")
        
        # Build metrics dictionary (exactly like calculations.py)
        metrics = {
            "YTD PnL": f"${ytd_pnl:,.2f}",
            "MTD PnL": f"${mtd_pnl:,.2f}",
            "Weekly PnL": f"${last_week_pnl:,.2f}",
            "% Change in Weekly PnL": f"{pnl_change:.2f}%" if pnl_change is not None else "N/A",
            "% Change in Weekly Volume": f"{volume_change:.2f}%" if volume_change is not None else "N/A",
            "Client Volume": f"${last_week_volume:,.2f}",
            "YTD Margin": f"{ytd_margin:.2%}" if ytd_margin is not None else "N/A",
            "Weekly Margin": f"{weekly_margin:.2%}" if weekly_margin is not None else "N/A",
            "Annualised run-rate for PnL": f"${annualized_pnl:,.2f}" if annualized_pnl is not None else "N/A"
        }
        
        print("✅ Calculations complete.")
        return metrics
        
    except Exception as e:
        print(f"Error in calculations: {e}")
        raise

def get_daily_pnl_data(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Get daily P&L data for charting
    """
    try:
        df = pd.read_csv(csv_file_path)
        df.columns = df.columns.str.strip()
        df = df[df["Order ID"] != 6315.0]
        df.rename(columns={"Revenue Received from Counterparty (USD)": "Volume (USD)"}, inplace=True)
        
        df["Total P&L (USD)"] = pd.to_numeric(
            df["Total P&L (USD)"].astype(str).str.replace(",", "").str.strip().replace("", "0"),
            errors="coerce"
        )
        df["Volume (USD)"] = pd.to_numeric(
            df["Volume (USD)"].astype(str).str.replace(",", "").str.strip().replace("", "0"),
            errors="coerce"
        )
        df["Booking Date"] = pd.to_datetime(df["Booking Date"], errors="coerce")
        df.dropna(subset=["Booking Date"], inplace=True)
        df = df[df["Booking Date"] <= cutoff_date]
        
        # Get last week data
        start_of_week = cutoff_date - timedelta(days=6)
        df_week = df[(df["Booking Date"] >= start_of_week) & (df["Booking Date"] <= cutoff_date)]
        
        # Group by date
        daily_data = df_week.groupby("Booking Date").agg({
            "Total P&L (USD)": "sum",
            "Volume (USD)": "sum"
        }).reset_index()
        
        return daily_data
        
    except Exception as e:
        print(f"Error getting daily P&L data: {e}")
        return pd.DataFrame()

def get_client_data(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Get client aggregation data for charts
    """
    try:
        df = pd.read_csv(csv_file_path)
        df.columns = df.columns.str.strip()
        df = df[df["Order ID"] != 6315.0]
        df.rename(columns={"Revenue Received from Counterparty (USD)": "Volume (USD)"}, inplace=True)
        
        df["Total P&L (USD)"] = pd.to_numeric(
            df["Total P&L (USD)"].astype(str).str.replace(",", "").str.strip().replace("", "0"),
            errors="coerce"
        )
        df["Volume (USD)"] = pd.to_numeric(
            df["Volume (USD)"].astype(str).str.replace(",", "").str.strip().replace("", "0"),
            errors="coerce"
        )
        df["Booking Date"] = pd.to_datetime(df["Booking Date"], errors="coerce")
        df.dropna(subset=["Booking Date"], inplace=True)
        df = df[df["Booking Date"] <= cutoff_date]
        
        # Get last week data
        start_of_week = cutoff_date - timedelta(days=6)
        df_week = df[(df["Booking Date"] >= start_of_week) & (df["Booking Date"] <= cutoff_date)]
        
        # Group by client
        client_data = df_week.groupby("Client Name").agg({
            "Total P&L (USD)": "sum",
            "Volume (USD)": "sum"
        }).reset_index()
        
        # Group by token (Client Leg 1)
        token_data = df_week.groupby("Client Leg 1").agg({
            "Total P&L (USD)": "sum", 
            "Volume (USD)": "sum"
        }).reset_index()
        
        return client_data, token_data
        
    except Exception as e:
        print(f"Error getting client data: {e}")
        return pd.DataFrame(), pd.DataFrame()