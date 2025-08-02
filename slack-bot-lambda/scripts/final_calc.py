import csv
from datetime import datetime, timedelta

def enrich_with_sell_pressure(
    flare_cache_file="flare_cache.csv",
    summary_file="daily_summary.csv",
    output_file="daily_summary_enriched.csv"
):
    # Load flare_cache.csv
    with open(flare_cache_file, newline="") as f:
        reader = csv.DictReader(f)
        flare_data = [
            {
                "Date": datetime.strptime(row["Date"], "%Y-%m-%d").date(),
                "Volume": float(row["Volume (FLR)"])
            }
            for row in reader
        ]

    flare_data.sort(key=lambda x: x["Date"])

    def rolling_30d_volume(end_date):
        start_date = end_date - timedelta(days=29)
        return sum(row["Volume"] for row in flare_data if start_date <= row["Date"] <= end_date)

    # Load daily_summary.csv
    with open(summary_file, newline="") as f:
        reader = csv.DictReader(f)
        summary_rows = list(reader)

    # Enrich rows
    for row in summary_rows:
        date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
        vol_sum = rolling_30d_volume(date)
        avg_daily_sell = vol_sum / 30 if vol_sum else 0
        total_quantity = float(row["Total Quantity"])
        sell_pressure = total_quantity / avg_daily_sell if avg_daily_sell else 0

        row["30D Volume Sum"] = round(vol_sum, 2)
        row["30D Avg Daily Sell"] = round(avg_daily_sell, 2)
        row["Sell Pressure Ratio"] = round(sell_pressure, 6)

    # Save enriched summary
    fieldnames = list(summary_rows[0].keys())
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print("Saved enriched summary to daily_summary_enriched.csv")
