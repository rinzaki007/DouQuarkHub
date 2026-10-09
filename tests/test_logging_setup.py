"""Regression tests for redaction of credentials in application logs."""
import logging

from moviesync.logging_setup import RedactingFormatter


def test_redacting_formatter_hides_labeled_secrets_and_authorization_headers():
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        "moviesync",
        logging.ERROR,
        __file__,
        1,
        'plugin failed: cookie="cookie-value" refresh_token=refresh-value '
        'Authorization: Bearer bearer-value password: plain-password',
        (),
        None,
    )

    output = formatter.format(record)

    for secret in (
        "cookie-value",
        "refresh-value",
        "bearer-value",
        "plain-password",
    ):
        assert secret not in output
    assert output.count("[REDACTED]") >= 4


def test_redacting_formatter_sanitizes_secrets_in_tracebacks():
    formatter = RedactingFormatter("%(message)s")
    try:
        raise RuntimeError('request failed: token="trace-token"')
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "moviesync",
            logging.ERROR,
            __file__,
            1,
            "plugin operation failed",
            (),
            sys.exc_info(),
        )

    output = formatter.format(record)

    assert "trace-token" not in output
    assert "RuntimeError" in output
    assert "[REDACTED]" in output
