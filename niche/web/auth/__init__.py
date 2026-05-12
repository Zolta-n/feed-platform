"""Web auth helpers — magic link generation and validation."""
from .magic_link import generate_magic_token, generate_hmac_token, verify_hmac_token

__all__ = ["generate_magic_token", "generate_hmac_token", "verify_hmac_token"]
