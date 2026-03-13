import os
from decimal import Decimal

import requests

from .integrations.jenga.signature import generate_balance_signature
from .integrations.jenga.token import get_merchant_access_token_from_env
from .models import BankBalanceSnapshot, JengaApiSettings


DEFAULT_BALANCE_ENDPOINT_BASE = (
    "https://uat.finserve.africa/v3-apis/account-api/v3.0/accounts/balances"
)


def _extract_value(payload, path, default=None):
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _extract_balance_amount(payload):
    # First try configured dot-path for backwards compatibility.
    configured_path = os.getenv("JENGA_BALANCE_FIELD_PATH", "balance")
    configured_value = _extract_value(payload, configured_path)
    if configured_value is not None:
        return configured_value

    # Finserve balance response shape:
    # {"data": {"balances": [{"amount": "...", "type": "Available"}, ...]}}
    balances = _extract_value(payload, "data.balances", default=[])
    if isinstance(balances, list) and balances:
        preferred_type = os.getenv("JENGA_BALANCE_TYPE", "Available").strip().lower()
        for item in balances:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).strip().lower()
            if item_type == preferred_type and item.get("amount") is not None:
                return item.get("amount")

        # Fallback to first balance amount if preferred type is absent.
        first = balances[0]
        if isinstance(first, dict) and first.get("amount") is not None:
            return first.get("amount")

    return "0.00"


def _get_jenga_access_token():
    return get_merchant_access_token_from_env()


def fetch_jenga_equity_balance():
    settings_obj = JengaApiSettings.objects.order_by("-updated_at", "-id").first()
    if not settings_obj or not settings_obj.account_reference:
        raise ValueError("Please set the receiving account reference in Settings first.")

    token = _get_jenga_access_token()
    account_ref = settings_obj.account_reference
    country_code = os.getenv("JENGA_SIGNATURE_COUNTRY_CODE", "KE")
    endpoint_base = os.getenv("JENGA_BALANCE_ENDPOINT", DEFAULT_BALANCE_ENDPOINT_BASE).rstrip("/")
    endpoint = endpoint_base
    if "{country_code}" in endpoint_base or "{account_reference}" in endpoint_base:
        endpoint = endpoint_base.format(country_code=country_code, account_reference=account_ref)
    else:
        endpoint = f"{endpoint_base}/{country_code}/{account_ref}"

    provider = os.getenv("JENGA_PROVIDER_NAME", "Jenga")

    headers = {
        "Authorization": f"Bearer {token}",
    }

    # Include signed account reference when private key-based signing is configured.
    signature_header = os.getenv("JENGA_SIGNATURE_HEADER", "signature")
    try:
        headers[signature_header] = generate_balance_signature(
            account_reference=account_ref,
            country_code=country_code,
        )
    except ValueError:
        # Keep backward compatibility for environments that have no private key yet.
        pass

    response = requests.get(endpoint, headers=headers, timeout=20)

    response.raise_for_status()
    data = response.json()

    raw_balance = _extract_balance_amount(data)
    balance = Decimal(str(raw_balance))
    return {
        "ok": True,
        "provider": provider,
        "account_reference": account_ref,
        "balance": balance,
        "raw": str(data),
    }


def fetch_and_store_jenga_equity_balance():
    result = fetch_jenga_equity_balance()
    snapshot = BankBalanceSnapshot.objects.create(
        provider=result["provider"],
        account_reference=result["account_reference"],
        balance=result["balance"],
        raw_response=result["raw"],
    )
    return result, snapshot
