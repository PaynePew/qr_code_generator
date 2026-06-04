import pytest
from sqlalchemy.exc import IntegrityError

from backend.token_generator import (
    MAX_RETRIES,
    TokenCollisionError,
    allocate_token,
    generate_token,
)

BASE62_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


NONCE_A = b"\x00" * 16
NONCE_B = b"\x01" * 16


class TestGenerateToken:
    def test_returns_7_char_string(self):
        token = generate_token("https://example.com", "secret", NONCE_A)
        assert len(token) == 7

    def test_all_chars_are_base62(self):
        token = generate_token("https://example.com", "secret", NONCE_A)
        assert all(c in BASE62_CHARS for c in token)

    def test_deterministic_same_inputs(self):
        t1 = generate_token("https://example.com", "secret", NONCE_A)
        t2 = generate_token("https://example.com", "secret", NONCE_A)
        assert t1 == t2

    def test_different_nonces_produce_different_tokens(self):
        t0 = generate_token("https://example.com", "secret", NONCE_A)
        t1 = generate_token("https://example.com", "secret", NONCE_B)
        assert t0 != t1

    def test_different_secrets_produce_different_tokens(self):
        t1 = generate_token("https://example.com", "secret1", NONCE_A)
        t2 = generate_token("https://example.com", "secret2", NONCE_A)
        assert t1 != t2

    def test_different_urls_produce_different_tokens(self):
        t1 = generate_token("https://example.com", "secret", NONCE_A)
        t2 = generate_token("https://other.com", "secret", NONCE_A)
        assert t1 != t2


class TestAllocateToken:
    def test_calls_try_insert_and_returns_token(self):
        inserted = []

        def try_insert(token):
            inserted.append(token)

        token = allocate_token("https://example.com", "secret", try_insert)
        assert len(token) == 7
        assert len(inserted) == 1
        assert inserted[0] == token

    def test_retries_on_integrity_error(self):
        call_count = [0]

        def try_insert(token):
            call_count[0] += 1
            if call_count[0] < 3:
                raise IntegrityError(None, None, Exception("UNIQUE constraint failed"))

        token = allocate_token("https://example.com", "secret", try_insert)
        assert call_count[0] == 3
        assert len(token) == 7

    def test_raises_after_max_retries(self):
        def try_insert(token):
            raise IntegrityError(None, None, Exception("UNIQUE constraint failed"))

        with pytest.raises(TokenCollisionError):
            allocate_token("https://example.com", "secret", try_insert)

    def test_each_retry_uses_different_nonce(self):
        tokens_tried = []

        def try_insert(token):
            tokens_tried.append(token)
            if len(tokens_tried) < 2:
                raise IntegrityError(None, None, Exception("UNIQUE constraint failed"))

        allocate_token("https://example.com", "secret", try_insert)
        assert tokens_tried[0] != tokens_tried[1]

    def test_same_url_repeated_4_times_returns_4_distinct_tokens_no_500(self):
        """Regression: submitting the same URL N>=4 times must mint N distinct tokens with no error."""
        minted: list[str] = []

        # Simulate a DB where previously-minted tokens cause IntegrityError on re-insert.
        def try_insert(token: str) -> None:
            if token in minted:
                raise IntegrityError(None, None, Exception("UNIQUE constraint failed"))
            minted.append(token)

        for _ in range(4):
            allocate_token("https://example.com", "secret", try_insert)

        assert len(minted) == 4
        assert len(set(minted)) == 4, "all 4 tokens must be distinct"

    def test_nonce_is_random_not_loop_index(self):
        """Each call to allocate_token must use a fresh random nonce, not a fixed sequence."""
        first_call_tokens: list[str] = []
        second_call_tokens: list[str] = []

        # Always fail so we collect all tokens tried per call.
        def try_insert_first(token: str) -> None:
            first_call_tokens.append(token)
            raise IntegrityError(None, None, Exception("UNIQUE constraint failed"))

        def try_insert_second(token: str) -> None:
            second_call_tokens.append(token)
            raise IntegrityError(None, None, Exception("UNIQUE constraint failed"))

        with pytest.raises(TokenCollisionError):
            allocate_token("https://example.com", "secret", try_insert_first)
        with pytest.raises(TokenCollisionError):
            allocate_token("https://example.com", "secret", try_insert_second)

        # If nonces were just range(MAX_RETRIES), both calls would try the exact same tokens.
        # With random nonces the sets should differ (with overwhelming probability).
        assert set(first_call_tokens) != set(second_call_tokens), (
            "Two independent allocate_token calls for the same URL must use different random "
            "nonces, not the same deterministic loop indices"
        )

    def test_max_retries_is_at_least_10(self):
        """Retry headroom must be generous enough for the random-nonce regime."""
        assert MAX_RETRIES >= 10
