import os
from decimal import Decimal

import requests

from .models import JengaApiSettings


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
        raise ValueError(
            "Missing Jenga API credentials in environment variables. Configure JENGA_API_TOKEN or auth credentials."
        )

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
    settings_obj = JengaApiSettings.objects.order_by("-updated_at", "-id").first()
    if not settings_obj or not settings_obj.account_reference:
        raise ValueError("Please set the receiving account reference in Settings first.")

    endpoint = os.getenv("JENGA_BALANCE_ENDPOINT")
    if not endpoint:
        raise ValueError("JENGA_BALANCE_ENDPOINT is missing in environment configuration.")

    token = _get_jenga_access_token()
    account_ref = settings_obj.account_reference
    http_method = os.getenv("JENGA_BALANCE_HTTP_METHOD", JengaApiSettings.HTTP_POST).upper()
    balance_path = os.getenv("JENGA_BALANCE_FIELD_PATH", "balance")
    provider = os.getenv("JENGA_PROVIDER_NAME", "Jenga")

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
