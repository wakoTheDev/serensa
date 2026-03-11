import os
from decimal import Decimal

import requests


def _extract_value(payload, path, default=None):
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _get_jenga_access_token():
    static_token = os.getenv("JENGA_API_TOKEN")
    if static_token:
        return static_token

    auth_endpoint = os.getenv("JENGA_AUTH_ENDPOINT")
    client_id = os.getenv("JENGA_CLIENT_ID")
    client_secret = os.getenv("JENGA_CLIENT_SECRET")

    if not auth_endpoint or not client_id or not client_secret:
        return None

    payload = {
        "grant_type": os.getenv("JENGA_GRANT_TYPE", "client_credentials"),
        "client_id": client_id,
        "client_secret": client_secret,
    }
    scope = os.getenv("JENGA_SCOPE")
    if scope:
        payload["scope"] = scope

    response = requests.post(auth_endpoint, data=payload, timeout=20)
    response.raise_for_status()
    token_data = response.json()

    access_token = token_data.get("access_token") or token_data.get("token")
    if not access_token:
        raise ValueError("Jenga auth response missing access token")
    return access_token


def fetch_jenga_equity_balance():
    """
    Fetches account balance via Jenga API.
    Falls back to a configurable mock when credentials are unavailable.
    """
    endpoint = os.getenv("JENGA_BALANCE_ENDPOINT")
    token = _get_jenga_access_token()
    account_ref = os.getenv("EQUITY_ACCOUNT_REF", "equity-main")
    http_method = os.getenv("JENGA_BALANCE_HTTP_METHOD", "POST").upper()
    balance_path = os.getenv("JENGA_BALANCE_FIELD_PATH", "balance")
    provider = os.getenv("JENGA_PROVIDER_NAME", "Jenga")

    if not endpoint or not token:
        mock_balance = Decimal(os.getenv("JENGA_MOCK_BALANCE", "0.00"))
        return {
            "ok": True,
            "provider": provider,
            "account_reference": account_ref,
            "balance": mock_balance,
            "raw": "mock response",
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    api_key = os.getenv("JENGA_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    payload = {"accountReference": account_ref}
    if http_method == "GET":
        response = requests.get(endpoint, params=payload, headers=headers, timeout=20)
    else:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=20)

    response.raise_for_status()
    data = response.json()

    raw_balance = _extract_value(data, balance_path, default="0.00")
    balance = Decimal(str(raw_balance))
    return {
        "ok": True,
        "provider": provider,
        "account_reference": account_ref,
        "balance": balance,
        "raw": str(data),
    }
