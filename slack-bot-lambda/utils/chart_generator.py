"""
Chart generation for P&L reports using matplotlib
Exactly matching WeeklyDeskPnL chart generation
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import matplotlib.ticker as mticker
from matplotlib.patches import ConnectionPatch
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import tempfile
import os

# Set matplotlib to use non-interactive backend
plt.switch_backend('Agg')

def generate_pnl_charts(cutoff_date, csv_file_path):
    """
    Generate all P&L charts exactly like WeeklyDeskPnL
    
    Args:
        cutoff_date (pd.Timestamp): Cutoff date for chart generation
        csv_file_path (str): Path to CSV export file
        
    Returns:
        dict: Dictionary with chart file paths matching WeeklyDeskPnL
    """
    try:
        chart_paths = {}
        
        # Generate cumulative daily P&L chart (plot.py)
        chart_paths['cumulative_daily_pnl'] = generate_cumulative_pnl_plot(cutoff_date, csv_file_path)
        print("✅ Cumulative PnL chart saved.")
        
        # Generate weekly bar plot (daily_week_plot.py)  
        chart_paths['weekly_pnl_volume'] = generate_weekly_bar_plot(cutoff_date, csv_file_path)
        print("✅ Weekly PnL and Volume chart saved.")
        
        # Generate top 10 bar charts (ranking_plot.py)
        client_chart, token_chart = generate_top10_bar_charts(cutoff_date, csv_file_path)
        chart_paths['top10_clients_pnl'] = client_chart
        chart_paths['top10_tokens_pnl'] = token_chart
        print("✅ Top Clients/Assets bar charts saved.")
        
        # Generate pie charts (pie_charts.py)
        pie_charts = generate_pie_charts(cutoff_date, csv_file_path)
        chart_paths.update(pie_charts)
        print("✅ Pie charts saved.")
        
        print(f"Generated {len(chart_paths)} charts successfully")
        return chart_paths
        
    except Exception as e:
        print(f"Error generating charts: {e}")
        return {}

def generate_cumulative_pnl_plot(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Generate cumulative P&L plot exactly like WeeklyDeskPnL/plot.py
    """
    try:
        # Load and clean data (exactly like plot.py)
        df = pd.read_csv(csv_file_path)
        df.columns = df.columns.str.strip()
        df["Booking Date"] = pd.to_datetime(df["Booking Date"], errors="coerce")
        df["Total P&L (USD)"] = pd.to_numeric(
            df["Total P&L (USD)"].astype(str).str.replace(",", ""), errors="coerce"
        )
        df.dropna(subset=["Booking Date", "Total P&L (USD)"], inplace=True)

        # Filter by cutoff (exactly like plot.py)
        df = df[df["Booking Date"] <= cutoff_date]
        df = df[df["Booking Date"].dt.year == cutoff_date.year]  # YTD only

        # Group daily PnL
        daily = df.groupby("Booking Date")["Total P&L (USD)"].sum().sort_index()
        cumulative = daily.cumsum()

        # Plot (exactly like plot.py)
        title_fontsize = 16
        label_fontsize = 13
        tick_fontsize = 11

        fig, ax1 = plt.subplots(figsize=(9, 5.5))
        ax2 = ax1.twinx()

        # Plot cumulative PnL (left axis)
        ax1.plot(daily.index, cumulative, label="Cumulative PnL", color="blue", linewidth=2)
        ax1.set_ylabel("Cumulative PnL ($USD)", fontsize=label_fontsize, color="blue")
        ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax1.tick_params(axis='y', labelcolor='blue', labelsize=tick_fontsize)
        ax1.tick_params(axis='x', labelsize=tick_fontsize)

        # Plot daily PnL (right axis)
        ax2.bar(daily.index, daily, width=0.8, alpha=0.4, label="Daily PnL", color="grey")
        ax2.set_ylabel("Daily PnL ($USD)", fontsize=label_fontsize, color="grey")
        ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax2.tick_params(axis='y', labelcolor='grey', labelsize=tick_fontsize)

        plt.tight_layout()
        plt.draw()

        # Align ax1 zero with ax2 zero (exactly like plot.py)
        zero_display_y = ax2.transData.transform((0, 0))[1]
        zero_data_ax1 = ax1.transData.inverted().transform((0, zero_display_y))[1]
        old_min, old_max = ax1.get_ylim()
        new_min = old_min - zero_data_ax1
        new_max = old_max - zero_data_ax1

        # Add 5% headroom to prevent line clipping
        range_pad = (new_max - new_min) * 0.17
        ax1.set_ylim(new_min, new_max + range_pad)

        # Layout and export
        plt.title(f"Cumulative & Daily PnL (YTD up to {cutoff_date.date()})", fontsize=title_fontsize)
        fig.autofmt_xdate()
        fig.tight_layout()
        plt.grid(axis='y', linestyle='--', alpha=0.3)
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png', prefix='cumulative_daily_pnl_')
        plt.savefig(temp_file.name, dpi=300)
        plt.close()
        
        return temp_file.name
        
    except Exception as e:
        print(f"Error creating cumulative P&L chart: {e}")
        plt.close()
        return None

def generate_weekly_bar_plot(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Generate weekly bar plot exactly like WeeklyDeskPnL/daily_week_plot.py
    """
    try:
        # Load and clean data (exactly like daily_week_plot.py)
        df = pd.read_csv(csv_file_path, parse_dates=["Booking Date"])
        df.columns = df.columns.str.strip()  # Clean column headers
        df.rename(columns={"Revenue Received from Counterparty (USD)": "Volume (USD)"}, inplace=True)

        df["Total P&L (USD)"] = pd.to_numeric(df["Total P&L (USD)"].astype(str).str.replace(",", ""), errors="coerce")
        df["Volume (USD)"] = pd.to_numeric(df["Volume (USD)"].astype(str).str.replace(",", ""), errors="coerce")

        # Ensure 'Booking Date' is datetime
        df['Booking Date'] = pd.to_datetime(df['Booking Date'])

        # Filter for the 7-day window ending on the cutoff date
        start = cutoff_date - timedelta(days=6)
        mask = (df['Booking Date'] >= start) & (df['Booking Date'] <= cutoff_date)
        df_week = df.loc[mask]

        # Group by date, sum PnL and Volume
        grouped = df_week.groupby('Booking Date').agg({'Total P&L (USD)': 'sum', 'Volume (USD)': 'sum'}).reset_index()

        # Add day name column
        grouped['Day'] = grouped['Booking Date'].dt.day_name()

        # Ensure correct order from Saturday to Friday
        days_order = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        grouped['Day'] = pd.Categorical(grouped['Day'], categories=days_order, ordered=True)

        # Reindex to include all days, filling missing with zeros
        grouped = grouped.set_index('Day').reindex(days_order, fill_value=0).reset_index()

        x = np.arange(len(grouped['Day']))  # label locations
        width = 0.35  # width of the bars

        # Fonts (exactly like daily_week_plot.py)
        title_fontsize = 16
        label_fontsize = 13
        tick_fontsize = 11

        fig, ax1 = plt.subplots(figsize=(9, 5.5))
        rects1 = ax1.bar(x - width/2, grouped["Total P&L (USD)"], width, label="Daily P&L", color='steelblue')
        ax1.set_ylabel("Daily PnL ($USD)", fontsize=label_fontsize, color='steelblue')
        ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax1.tick_params(axis='y', labelcolor='steelblue', labelsize=tick_fontsize)
        ax1.tick_params(axis='x', labelsize=tick_fontsize)

        ax2 = ax1.twinx()
        rects2 = ax2.bar(x + width/2, grouped["Volume (USD)"], width, label="Volume", color="#EA4336")
        ax2.set_ylabel("Volume ($USD)", fontsize=label_fontsize, color="#EA4336")
        ax2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax2.tick_params(axis='y', labelcolor="#EA4336", labelsize=tick_fontsize)

        ax1.set_xticks(x)
        ax1.set_xticklabels(grouped['Day'], rotation=30, ha='right')

        plt.title(f"Daily PnL & Volume ({start.date()} to {cutoff_date.date()})", fontsize=title_fontsize)
        fig.tight_layout()
        plt.grid(axis='y', linestyle='--', alpha=0.3)
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png', prefix='weekly_pnl_volume_')
        plt.savefig(temp_file.name, dpi=300)
        plt.close()
        
        return temp_file.name
        
    except Exception as e:
        print(f"Error creating weekly bar plot: {e}")
        plt.close()
        return None

def plot_dual_axis_bar(data: pd.DataFrame, title: str, filename_prefix: str):
    """
    Plot dual axis bar chart exactly like WeeklyDeskPnL/ranking_plot.py
    """
    if data.empty:
        return None

    def currency_short(x, _):
        if x >= 1_000_000:
            return f"${x/1_000_000:.1f}M"
        elif x >= 1_000:
            return f"${x/1_000:.0f}K"
        else:
            return f"${x:,.0f}"

    # Font sizes (exactly like ranking_plot.py)
    title_fontsize = 16
    label_fontsize = 13
    tick_fontsize = 12

    # Figure and axes
    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax2 = ax1.twinx()

    width = 0.4
    x = range(len(data.index))

    # Left axis: PnL
    ax1.bar([i - width / 2 for i in x], data["PnL"], width=width, label="PnL", color="steelblue")
    ax1.set_ylabel("PnL (USD)", fontsize=label_fontsize, color="steelblue")
    ax1.tick_params(axis='y', labelcolor='steelblue', labelsize=tick_fontsize)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(currency_short))

    # Right axis: Volume
    ax2.bar([i + width / 2 for i in x], data["Volume"], width=width, label="Volume", color="#EA4336")
    ax2.set_ylabel("Volume (USD)", fontsize=label_fontsize, color="#EA4336")
    ax2.tick_params(axis='y', labelcolor="#EA4336", labelsize=tick_fontsize)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(currency_short))

    # X-axis
    ax1.set_xticks(x)
    ax1.set_xticklabels(data.index, rotation=45, ha='right', fontsize=tick_fontsize)
    ax1.tick_params(axis='x', labelsize=tick_fontsize)

    # Title and legends
    ax1.set_title(title, fontsize=title_fontsize)
    ax1.legend(loc='upper left', fontsize=10)
    ax2.legend(loc='upper right', fontsize=10)

    # Layout and save
    ax1.grid(axis='y', linestyle='--', alpha=0.3)
    fig.subplots_adjust(bottom=0.25)
    fig.tight_layout()
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png', prefix=filename_prefix)
    plt.savefig(temp_file.name, dpi=300)
    plt.close()
    
    return temp_file.name

def generate_top10_bar_charts(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Generate top 10 bar charts exactly like WeeklyDeskPnL/ranking_plot.py
    """
    try:
        df = pd.read_csv(csv_file_path)
        df.columns = df.columns.str.strip()
        df["Booking Date"] = pd.to_datetime(df["Booking Date"], errors="coerce")
        df["Total P&L (USD)"] = pd.to_numeric(df["Total P&L (USD)"].astype(str).str.replace(",", ""), errors="coerce")
        df["Revenue Received from Counterparty (USD)"] = pd.to_numeric(
            df["Revenue Received from Counterparty (USD)"].astype(str).str.replace(",", ""), errors="coerce"
        )
        df.rename(columns={"Revenue Received from Counterparty (USD)": "Volume (USD)"}, inplace=True)

        df["Client Name"] = df["Client Name"].astype(str).str.strip()
        df["Client Leg 1"] = df["Client Leg 1"].astype(str).str.strip()
        df.dropna(subset=["Booking Date", "Total P&L (USD)", "Volume (USD)"], inplace=True)

        start = cutoff_date - timedelta(days=6)
        df = df[(df["Booking Date"] >= start) & (df["Booking Date"] <= cutoff_date)]

        # Top 10 Clients by PnL and Volume (exactly like ranking_plot.py)
        df["Client Short"] = df["Client Name"].str.split().str[0]
        top_clients_pnl = df.groupby("Client Short")["Total P&L (USD)"].sum()
        top_clients_volume = df.groupby("Client Short")["Volume (USD)"].sum()

        top_clients_combined = pd.DataFrame({
            "PnL": top_clients_pnl,
            "Volume": top_clients_volume
        }).fillna(0)

        top_clients_combined = top_clients_combined.sort_values("PnL", ascending=False).head(10)
        client_chart = plot_dual_axis_bar(
            top_clients_combined,
            title="Client PnL and Volume",
            filename_prefix="top10_clients_pnl_"
        )

        # Top 10 Tokens by PnL and Volume (exactly like ranking_plot.py)
        top_tokens_pnl = df.groupby("Client Leg 1")["Total P&L (USD)"].sum()
        top_tokens_volume = df.groupby("Client Leg 1")["Volume (USD)"].sum()

        top_tokens_combined = pd.DataFrame({
            "PnL": top_tokens_pnl,
            "Volume": top_tokens_volume
        }).fillna(0)

        top_tokens_combined = top_tokens_combined.sort_values("PnL", ascending=False).head(10)
        token_chart = plot_dual_axis_bar(
            top_tokens_combined,
            title="Token PnL and Volume",
            filename_prefix="top10_tokens_pnl_"
        )
        
        return client_chart, token_chart
        
    except Exception as e:
        print(f"Error creating top 10 bar charts: {e}")
        return None, None

def plot_pie(df, group_col, value_col, title, filename_prefix, min_pct=4):
    """
    Plot pie chart exactly like WeeklyDeskPnL/pie_charts.py
    """
    try:
        # If plotting clients, cut name to first word (exactly like pie_charts.py)
        if group_col == "Client Name":
            df = df.copy()
            df["Client Name"] = df["Client Name"].astype(str).str.split().str[0]

        grouped = df.groupby(group_col)[value_col].sum().sort_values(ascending=False)
        total = grouped.sum()

        if total == 0 or grouped.empty:
            print(f"⚠️ Skipping {title} — no data to plot.")
            return None

        pct = (grouped / total) * 100
        top = grouped[pct >= min_pct]
        others = grouped[pct < min_pct].sum()
        if others > 0:
            top["Others"] = others

        fig, ax = plt.subplots(figsize=(8, 6))
        wedges, texts = ax.pie(
            top,
            labels=None,
            autopct=None,
            startangle=90,
            radius=0.85,
            wedgeprops={"edgecolor": "white"}
        )

        for wedge, name, value in zip(wedges, top.index, top.values):
            angle = (wedge.theta2 + wedge.theta1) / 2
            x = np.cos(np.deg2rad(angle))
            y = np.sin(np.deg2rad(angle))
            label_x = 1.1 * x
            label_y = 1.1 * y

            percentage = (value / total) * 100
            label = f"{name}\n{percentage:.1f}%"

            ax.text(label_x, label_y, label,
                    ha='center', va='center',
                    fontsize=15, color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="none", ec="none", alpha=0))  # Transparent background

            con = ConnectionPatch(
                xyA=(x * 0.85, y * 0.85),
                coordsA=ax.transData,
                xyB=(label_x, label_y),
                coordsB=ax.transData,
                arrowstyle="-", color="gray", lw=0.8
            )
            ax.add_artist(con)

        ax.set_title(title, fontsize=18)
        plt.tight_layout()
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png', prefix=filename_prefix)
        plt.savefig(temp_file.name, dpi=300)
        plt.close()
        
        return temp_file.name
        
    except Exception as e:
        print(f"Error creating pie chart {title}: {e}")
        plt.close()
        return None

def generate_pie_charts(cutoff_date: pd.Timestamp, csv_file_path: str):
    """
    Generate pie charts exactly like WeeklyDeskPnL/pie_charts.py
    """
    try:
        df = pd.read_csv(csv_file_path, parse_dates=["Booking Date"])

        df["Total P&L (USD) "] = pd.to_numeric(
            df["Total P&L (USD) "].astype(str).str.replace(",", ""), errors="coerce"
        )
        df["Volume (USD)"] = pd.to_numeric(
            df["Revenue Received from Counterparty (USD)"].astype(str).str.replace(",", ""), errors="coerce"
        )

        df.dropna(subset=["Booking Date", "Total P&L (USD) ", "Volume (USD)"], inplace=True)

        start = cutoff_date - timedelta(days=6)
        df = df[(df["Booking Date"] >= start) & (df["Booking Date"] <= cutoff_date)]

        pie_charts = {}
        
        # Token P&L pie chart
        pie_charts['token_pnl_pie'] = plot_pie(
            df, "Client Leg 1", "Total P&L (USD) ",
            f"Token PnL Share ({start.date()} to {cutoff_date.date()})",
            "token_pnl_pie_"
        )

        # Token Volume pie chart
        pie_charts['token_volume_pie'] = plot_pie(
            df, "Client Leg 1", "Volume (USD)",
            f"Token Volume Share ({start.date()} to {cutoff_date.date()})",
            "token_volume_pie_"
        )

        # Client P&L pie chart
        pie_charts['client_pnl_pie'] = plot_pie(
            df, "Client Name", "Total P&L (USD) ",
            f"Client PnL Share ({start.date()} to {cutoff_date.date()})",
            "client_pnl_pie_"
        )

        # Client Volume pie chart
        pie_charts['client_volume_pie'] = plot_pie(
            df, "Client Name", "Volume (USD)",
            f"Client Volume Share ({start.date()} to {cutoff_date.date()})",
            "client_volume_pie_"
        )
        
        # Filter out None values
        pie_charts = {k: v for k, v in pie_charts.items() if v is not None}
        
        return pie_charts
        
    except Exception as e:
        print(f"Error generating pie charts: {e}")
        return {}

def cleanup_chart_files(chart_paths):
    """
    Clean up temporary chart files
    """
    try:
        for chart_type, file_path in chart_paths.items():
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                print(f"Cleaned up chart file: {chart_type}")
    except Exception as e:
        print(f"Error cleaning up chart files: {e}")