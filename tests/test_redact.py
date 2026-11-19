import pytest

from vault_zeta.redact import SecretInVault, assert_clean, find_secret, mask


def test_find_secret_openai_key():
    assert find_secret("my key is sk-1234567890abcdef12345678") == "openai-style key"


def test_find_secret_github_token():
    assert find_secret("token: ghp_123456789012345678901234567890") == "github token"


def test_find_secret_clean():
    assert find_secret("this is a clean sentence about postgres and redis") is None


def test_assert_clean_raises():
    with pytest.raises(SecretInVault):
        assert_clean("AWS key: AKIA1234567890123456")


def test_mask():
    masked = mask("key is sk-1234567890abcdef12345678 in config")
    assert "sk-" not in masked
    assert "[REDACTED]" in masked
