import requests
import json
import pandas as pd
from datetime import datetime, timezone
import os

def get_flr_volume_data(cache_file="flare_cache.csv", config_path="setup.json"):
    # Load API key
    try:
        with open(config_path, "r") as file:
            config = json.load(file)
            api_key = config.get("api_key")
            if not api_key:
                raise ValueError("API key not found in setup.json")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Configuration error: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {e}")

    url = "https://api.coingecko.com/api/v3/coins/flare-networks/market_chart?vs_currency=usd&days=90&interval=daily"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": api_key
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Parse timestamps
        prices = [(datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d'), p[1]) for p in data.get('prices', [])]
        market_caps = [m[1] for m in data.get('market_caps', [])]
        volumes = [v[1] for v in data.get('total_volumes', [])]

        new_df = pd.DataFrame(prices, columns=['Date', 'Price'])
        new_df['Market Cap'] = market_caps
        new_df['Volume'] = volumes
        new_df['Volume (FLR)'] = new_df['Volume'] / new_df['Price']

        # Merge with cache
        if os.path.exists(cache_file):
            existing_df = pd.read_csv(cache_file)
            combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset='Date').sort_values('Date')
        else:
            combined_df = new_df

        combined_df.to_csv(cache_file, index=False)
        return combined_df

    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {e}")
    except Exception as e:
        raise RuntimeError(f"Data processing error: {e}")
