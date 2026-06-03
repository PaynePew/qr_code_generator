import hashlib
import secrets
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
TOKEN_LEN = 7
MAX_RETRIES = 10


class TokenCollisionError(Exception):
    pass


def generate_token(url: str, secret: str, nonce: bytes) -> str:
    """Derive a 7-char Base62 token from url, secret, and a random nonce."""
    data = url.encode() + secret.encode() + nonce
    digest = hashlib.sha256(data).digest()
    n = int.from_bytes(digest, "big")
    chars = []
    while n:
        chars.append(BASE62[n % 62])
        n //= 62
    b62 = "".join(reversed(chars)) if chars else BASE62[0]
    return b62[:TOKEN_LEN].ljust(TOKEN_LEN, BASE62[0])


def allocate_token(url: str, secret: str, try_insert: Callable[[str], None]) -> str:
    """Mint a unique token for url, retrying on collision with a fresh random nonce each time.

    Uses a cryptographically random 16-byte nonce per attempt so that submitting the same URL
    multiple times always yields distinct tokens.  The retry loop only handles the astronomically
    unlikely case where two different nonces happen to produce the same 7-char token hash.
    """
    for _ in range(MAX_RETRIES):
        nonce = secrets.token_bytes(16)
        token = generate_token(url, secret, nonce)
        try:
            try_insert(token)
            return token
        except IntegrityError:
            pass
    raise TokenCollisionError(f"Failed to allocate unique token after {MAX_RETRIES} retries")
