"""Unit tests for configuration validation.

INVARIANT PROTECTION: Configuration security boundaries
"""

import pytest
from pydantic import ValidationError

from argus.models import ServerConfig


def test_empty_api_key_list_validation() -> None:
    """
    INVARIANT: Empty API key list prevents server startup
    BREAKS: Security bypass - all requests would pass authentication

    Tester-discovered invariant: Developer validated keys against list
    but didn't verify list isn't empty. This test ensures misconfigured
    servers cannot start with zero API keys.
    """
    # Attempt to create ServerConfig with empty API key list
    with pytest.raises(ValidationError) as exc_info:
        ServerConfig(
            host="127.0.0.1",
            port=8765,
            api_keys=[],  # Empty list should be rejected
        )

    # Verify the validation error mentions api_keys
    error_dict = exc_info.value.errors()[0]
    assert error_dict["loc"] == ("api_keys",)
    assert "min_length" in error_dict["type"] or "at least" in str(error_dict)


def test_api_keys_must_be_unique() -> None:
    """
    INVARIANT: API keys must be unique in configuration
    BREAKS: Duplicate keys could indicate configuration error

    Developer-discovered invariant: Pydantic validator ensures uniqueness
    """
    # Attempt to create ServerConfig with duplicate API keys
    with pytest.raises(ValidationError) as exc_info:
        ServerConfig(
            host="127.0.0.1",
            port=8765,
            api_keys=["key1", "key1", "key2"],  # Duplicate key1
        )

    # Verify validation error
    error = str(exc_info.value)
    assert "unique" in error.lower()
