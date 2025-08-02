import datetime
import hmac
import hashlib
import base64
import json

def generate_auth_headers(method, path, query="", body="", config_path="setup.json"):

    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Error reading setup.json: {e}")

    api_key = config.get("talos_api_key")
    api_secret = config.get("talos_api_secret")
    host = config.get("taloshost")

    if not all([api_key, api_secret, host]):
        raise ValueError("Missing Talos API credentials or host in setup.json")

    utc_datetime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000000Z")

    params = [method, utc_datetime, host, path]
    if query:
        params.append(query)
    if body:
        params.append(body)

    payload = "\n".join(params)
    signature = base64.urlsafe_b64encode(
        hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).digest()
    ).decode()

    headers = {
        "TALOS-KEY": api_key,
        "TALOS-SIGN": signature,
        "TALOS-TS": utc_datetime,
    }

    return headers, host
