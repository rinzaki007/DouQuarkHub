from moviesync.regex_safety import has_nested_unbounded_quantifier
from moviesync.services.filename_rules import DEFAULT_TV_MAGIC_REGEX


def test_detects_common_nested_unbounded_repetitions():
    for pattern in (r"(.+)+$", r"(a*)+", r"(?:a+)+", r"((a+))+"):
        assert has_nested_unbounded_quantifier(pattern) is True


def test_allows_default_and_common_bounded_episode_patterns():
    assert has_nested_unbounded_quantifier(DEFAULT_TV_MAGIC_REGEX["pattern"]) is False
    assert has_nested_unbounded_quantifier(r"(?i)\bS\d{2}E\d{2}\b") is False
    assert has_nested_unbounded_quantifier(r"(?:foo|bar)+") is False


def test_escaped_quantifiers_and_character_classes_are_not_misclassified():
    assert has_nested_unbounded_quantifier(r"\(a\+\)+") is False
    assert has_nested_unbounded_quantifier(r"[+*]+") is False
