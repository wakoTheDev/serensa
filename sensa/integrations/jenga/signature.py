import os
from base64 import b64encode

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5


DEFAULT_COUNTRY_CODE = "KE"


def _load_private_key_pem():
    private_key_pem = (
        os.getenv("JENGA_PRIVATE_KEY")
        or os.getenv("PRIVATE_KEY")
        or os.getenv("FINSERVE_PRIVATE_KEY")
    )
    if private_key_pem:
        # Vercel env values may store new lines escaped.
        return private_key_pem.replace("\\n", "\n")

    private_key_path = os.getenv("JENGA_PRIVATE_KEY_PATH", "privatekey.pem")
    if os.path.exists(private_key_path):
        with open(private_key_path, "r", encoding="utf-8") as key_file:
            return key_file.read()

    raise ValueError(
        "Missing private key for signature generation. Set JENGA_PRIVATE_KEY/FINSERVE_PRIVATE_KEY "
        "or provide JENGA_PRIVATE_KEY_PATH."
    )


def build_balance_signature_message(account_reference, country_code=DEFAULT_COUNTRY_CODE):
    if not account_reference:
        raise ValueError("account_reference is required to build signature message")

    return f"{country_code}{account_reference}".encode("utf-8")


def generate_balance_signature(account_reference, country_code=DEFAULT_COUNTRY_CODE):
    message = build_balance_signature_message(account_reference, country_code=country_code)

    digest = SHA256.new()
    digest.update(message)

    private_key = RSA.import_key(_load_private_key_pem())
    signer = PKCS1_v1_5.new(private_key)
    sig_bytes = signer.sign(digest)
    return b64encode(sig_bytes).decode("utf-8")
