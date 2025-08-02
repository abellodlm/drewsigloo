def generate_execution_report(order_ids, market_data_file="flare_cache.csv", cutoff_hour=16):
    import requests
    import csv
    from auth import generate_auth_headers
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict
    import pandas as pd

    method = "GET"
    base_path = "/v1/trade-analytics"
    limit = 500
    all_data = []

    for order_id in order_ids:
        print(f"\nFetching data for Order ID: {order_id}")
        after_token = None
        seen_tokens = set()
        batch = 1

        while True:
            query = f"OrderID={order_id}&limit={limit}&TradedMarketOnly=True"
            if after_token:
                query += f"&after={after_token}"

            headers, host = generate_auth_headers(method, base_path, query=query)
            endpoint = f"https://{host}{base_path}?{query}"
            response = requests.get(url=endpoint, headers=headers)
            print(f"  Batch {batch} - Status: {response.status_code}")

            if response.status_code != 200:
                raise RuntimeError(f"Request failed for Order ID {order_id}")

            resp_json = response.json()
            data = resp_json.get("data", [])
            all_data.extend(data)

            after_token = resp_json.get("next")
            if not after_token or after_token in seen_tokens:
                break
            seen_tokens.add(after_token)
            batch += 1

    if not all_data:
        raise RuntimeError("No execution data retrieved.")

    # === Save raw CSV
    fieldnames = sorted(set().union(*(d.keys() for d in all_data)))
    with open("order.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_data)
    print(f"\nSaved {len(all_data)} records to order.csv")

    # === Daily Aggregation (with custom cutoff)
    daily = defaultdict(lambda: {
        "quantity_sum": 0.0,
        "amount_sum": 0.0,
        "fee_sum": 0.0,
        "weighted_price_sum": 0.0
    })

    for row in all_data:
        try:
            ts = row.get("Timestamp") or row.get("TransactTime")
            dt = datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=timezone.utc)

            if cutoff_hour in (0, 24):
                adjusted_dt = dt
            else:
                adjusted_dt = dt - timedelta(hours=24 - cutoff_hour)

            date = adjusted_dt.date()

            # ✅ Debug line to verify aggregation date
            #print(f"[DEBUG] Raw: {ts}, UTC: {dt}, Cutoff Applied: {adjusted_dt}, Aggregated Date: {date}")

            # Continue with aggregation
            qty = float(row.get("Quantity", 0))
            amt = float(row.get("Amount", 0))
            fee = float(row.get("Fee", 0))
            price = float(row.get("Price", 0))

            daily[date]["quantity_sum"] += qty
            daily[date]["amount_sum"] += amt
            daily[date]["fee_sum"] += fee
            daily[date]["weighted_price_sum"] += price * qty
        except Exception as e:
            print(f"Skipped row due to error: {e}")


    summary_rows = []
    for date, data in sorted(daily.items()):
        quantity = data["quantity_sum"]
        avg_price = data["weighted_price_sum"] / quantity if quantity else 0
        summary_rows.append({
            "Date": date.isoformat(),
            "Total Quantity": round(quantity, 6),
            "Total Amount": round(data["amount_sum"], 6),
            "Average Price": round(avg_price, 6),
            "Total Fees": round(data["fee_sum"], 6),
        })

    with open("daily_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)

    print("Saved daily summary to daily_summary.csv")

    # === Enrich with market data
    market_df = pd.read_csv(market_data_file, parse_dates=["Date"])
    market_df["Date"] = market_df["Date"].dt.date
    market_df = market_df.sort_values("Date")
    market_df["30D Volume Sum"] = market_df["Volume"].rolling(window=30, min_periods=1).sum()
    market_df["30D Volume Avg"] = market_df["30D Volume Sum"] / 30

    summary_df = pd.read_csv("daily_summary.csv", parse_dates=["Date"])
    summary_df["Date"] = summary_df["Date"].dt.date

    final_df = summary_df.merge(
        market_df[["Date", "30D Volume Sum", "30D Volume Avg"]],
        on="Date", how="left"
    )
    final_df.to_csv("daily_summary_enriched.csv", index=False)
    print("Saved enriched summary to daily_summary_enriched.csv")
