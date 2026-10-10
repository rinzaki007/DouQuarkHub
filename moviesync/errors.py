"""Shared platform-independent errors for MovieSync cards and services."""


class ConfigValidationError(ValueError):
    """Raised when persisted or submitted configuration is invalid."""
