import os

import requests


DEFAULT_MERCHANT_AUTH_ENDPOINT = (
    "https://uat.finserve.africa/authentication/api/v3/authenticate/merchant"
)


def request_merchant_access_token(
    api_key,
    merchant_code,
    consumer_secret,
    auth_endpoint=DEFAULT_MERCHANT_AUTH_ENDPOINT,
    timeout=20,
):
    if not api_key:
        raise ValueError("Missing api_key for merchant authentication")
    if not merchant_code:
        raise ValueError("Missing merchant_code for merchant authentication")
    if not consumer_secret:
        raise ValueError("Missing consumer_secret for merchant authentication")

    headers = {
        "Content-Type": "application/json",
        "Api-Key": api_key,
    }
    payload = {
        "merchantCode": merchant_code,
        "consumerSecret": consumer_secret,
    }

    response = requests.post(auth_endpoint, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    token_data = response.json()

    access_token = (
        token_data.get("accessToken")
        or token_data.get("access_token")
        or token_data.get("token")
    )
    if not access_token and isinstance(token_data.get("data"), dict):
        data = token_data["data"]
        access_token = data.get("accessToken") or data.get("access_token")

    if not access_token:
        raise ValueError("Merchant auth response missing access token")

    return access_token


def get_merchant_access_token_from_env():
    api_key = os.getenv("JENGA_API_KEY") or os.getenv("FINSERVE_API_KEY")
    merchant_code = os.getenv("JENGA_MERCHANT_CODE") or os.getenv("FINSERVE_MERCHANT_CODE")
    consumer_secret = os.getenv("JENGA_CONSUMER_SECRET") or os.getenv("FINSERVE_CONSUMER_SECRET")
    auth_endpoint = (
        os.getenv("JENGA_MERCHANT_AUTH_ENDPOINT")
        or DEFAULT_MERCHANT_AUTH_ENDPOINT
    )

    return request_merchant_access_token(
        api_key=api_key,
        merchant_code=merchant_code,
        consumer_secret=consumer_secret,
        auth_endpoint=auth_endpoint,
    )
