import pandas as pd

# Parameters
target_amount = 10_000_000  # FLR to sell

# Load flare market data
df = pd.read_csv("flare_cache.csv", parse_dates=["Date"])
df = df.sort_values("Date")
df["Volume (FLR)"] = df["Volume (FLR)"].astype(float)

# Last 30 days volume data
last_30_days = df[df["Date"] >= (df["Date"].max() - pd.Timedelta(days=29))]
total_volume = last_30_days["Volume (FLR)"].sum()
avg_volume = last_30_days["Volume (FLR)"].mean()
threshold_per_day = avg_volume * 0.005

# Days needed to sell target amount 
days_needed = target_amount / threshold_per_day

# Per-minute sell limit (assuming 24h execution)
minutes_per_day = 24 * 60
per_minute_limit = threshold_per_day / minutes_per_day

# Output
print(f"Total FLR volume (last 30 days): {total_volume:,.2f}")
print(f"30-day average daily volume (FLR): {avg_volume:,.2f}")
print(f"0.5% daily threshold: {threshold_per_day:,.2f}")
print(f"Days needed to sell {target_amount:,.0f} FLR without exceeding 0.5% per day: {days_needed:,.2f}")
print(f"Max FLR sell per minute (at 0.5% daily threshold, 24h execution): {per_minute_limit:,.6f}")
