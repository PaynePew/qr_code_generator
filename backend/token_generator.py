import hashlib
from sqlalchemy.exc import IntegrityError

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
TOKEN_LEN = 7
MAX_RETRIES = 3


class TokenCollisionError(Exception):
    pass


def generate_token(url: str, secret: str, nonce: int) -> str:
    data = (url + secret + str(nonce)).encode()
    digest = hashlib.sha256(data).digest()
    n = int.from_bytes(digest, "big")
    chars = []
    while n:
        chars.append(BASE62[n % 62])
        n //= 62
    b62 = "".join(reversed(chars)) if chars else BASE62[0]
    return b62[:TOKEN_LEN].ljust(TOKEN_LEN, BASE62[0])


def allocate_token(url: str, secret: str, try_insert) -> str:
    for nonce in range(MAX_RETRIES):
        token = generate_token(url, secret, nonce)
        try:
            try_insert(token)
            return token
        except IntegrityError:
            pass
    raise TokenCollisionError(f"Failed to allocate unique token after {MAX_RETRIES} retries")
