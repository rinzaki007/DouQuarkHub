"""Helpers for distinguishing definite transfer failures from ambiguous outcomes."""

UNCERTAIN_TRANSFER_MARKER = "转存结果不确定"


def is_uncertain_transfer_message(message: object) -> bool:
    """Return True when a failed transfer may nevertheless have completed remotely."""
    text = str(message or "").lower()
    if UNCERTAIN_TRANSFER_MARKER.lower() in text:
        return True
    ambiguous_phrases = (
        "timed out", "timeout", "connection reset", "connection aborted",
        "remote end closed", "connection error", "read timeout",
        "请求超时", "连接重置", "连接中断",
    )
    return any(phrase in text for phrase in ambiguous_phrases)
