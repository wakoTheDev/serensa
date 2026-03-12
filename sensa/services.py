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


def _get_jenga_access_token(settings_obj):
    static_token = settings_obj.api_token.strip()
    if static_token:
        return static_token

    auth_endpoint = settings_obj.auth_endpoint
    client_id = settings_obj.client_id
    client_secret = settings_obj.client_secret

    if not auth_endpoint or not client_id or not client_secret:
        raise ValueError("Jenga settings are incomplete. Configure API credentials first.")

    payload = {
        "grant_type": settings_obj.grant_type or "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    scope = settings_obj.scope
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
    if not settings_obj or not settings_obj.is_configured:
        raise ValueError("Configure Jenga account settings before fetching balances.")

    endpoint = settings_obj.balance_endpoint
    token = _get_jenga_access_token(settings_obj)
    account_ref = settings_obj.account_reference
    http_method = (settings_obj.balance_http_method or JengaApiSettings.HTTP_POST).upper()
    balance_path = settings_obj.balance_field_path or "balance"
    provider = settings_obj.provider_name or "Jenga"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    api_key = settings_obj.api_key
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
