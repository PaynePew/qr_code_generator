import pytest
from sqlalchemy.exc import IntegrityError
from backend.token_generator import generate_token, allocate_token, TokenCollisionError

BASE62_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


class TestGenerateToken:
    def test_returns_7_char_string(self):
        token = generate_token("https://example.com", "secret", 0)
        assert len(token) == 7

    def test_all_chars_are_base62(self):
        token = generate_token("https://example.com", "secret", 0)
        assert all(c in BASE62_CHARS for c in token)

    def test_deterministic_same_inputs(self):
        t1 = generate_token("https://example.com", "secret", 0)
        t2 = generate_token("https://example.com", "secret", 0)
        assert t1 == t2

    def test_different_nonces_produce_different_tokens(self):
        t0 = generate_token("https://example.com", "secret", 0)
        t1 = generate_token("https://example.com", "secret", 1)
        assert t0 != t1

    def test_different_secrets_produce_different_tokens(self):
        t1 = generate_token("https://example.com", "secret1", 0)
        t2 = generate_token("https://example.com", "secret2", 0)
        assert t1 != t2

    def test_different_urls_produce_different_tokens(self):
        t1 = generate_token("https://example.com", "secret", 0)
        t2 = generate_token("https://other.com", "secret", 0)
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
