import pytest

from renderer.naming import slugify


# --- normal cases ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello", "hello"),
        ("Hello World", "hello_world"),
        ("Order ID", "order_id"),
        ("already_snake_case", "already_snake_case"),
        ("Multiple   Spaces", "multiple_spaces"),
        ("Hello!!!World", "hello_world"),  # a run of non-alnum collapses to one "_"
        ("  Hello  ", "hello"),  # leading/trailing separators are stripped, not kept
        ("Mixed-Case_And.Dots", "mixed_case_and_dots"),
    ],
)
def test_slugify_normal_cases(text, expected):
    assert slugify(text) == expected


# --- digit-leading guard ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("123abc", "_123abc"),
        ("123", "_123"),
        ("3D Viewer", "_3d_viewer"),
    ],
)
def test_slugify_prefixes_underscore_when_digit_leading(text, expected):
    assert slugify(text) == expected
    assert slugify(text).isidentifier()


@pytest.mark.unit
def test_slugify_does_not_prefix_when_not_digit_leading():
    # sanity check that the digit guard is conditional, not unconditional
    assert not slugify("abc123").startswith("_")


# --- fully-empty vs digit-leading distinction ---

@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "!!!", "___", "---", "..."])
def test_slugify_raises_when_no_usable_characters(text):
    with pytest.raises(ValueError, match="no usable characters"):
        slugify(text)


@pytest.mark.unit
def test_slugify_does_not_raise_when_digit_leading_but_has_content():
    # a leading digit is a recoverable case (prefix "_"), distinct from the
    # unrecoverable fully-empty case (raise) - this is the key distinction
    # naming.py draws.
    assert slugify("1") == "_1"


# --- non-ASCII: only a-z0-9 survive, everything else is a separator ---

@pytest.mark.unit
def test_slugify_strips_non_ascii_letters():
    assert slugify("Café") == "caf"


@pytest.mark.unit
def test_slugify_raises_when_only_non_ascii_characters():
    with pytest.raises(ValueError, match="no usable characters"):
        slugify("日本語")


# --- idempotency ---

@pytest.mark.unit
def test_slugify_is_idempotent_on_its_own_output():
    once = slugify("Order ID")
    assert slugify(once) == once
