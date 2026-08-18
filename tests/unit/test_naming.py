import pytest

from renderer.naming import pascal_case_identifier, slugify


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


# --- pascal_case_identifier: normal cases ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello", "Hello"),
        ("Hello World", "HelloWorld"),
        ("Order ID", "OrderId"),
        ("already_snake_case", "AlreadySnakeCase"),
        ("Multiple   Spaces", "MultipleSpaces"),
        ("Hello!!!World", "HelloWorld"),
        ("  Hello  ", "Hello"),
        ("Mixed-Case_And.Dots", "MixedCaseAndDots"),
    ],
)
def test_pascal_case_identifier_normal_cases(text, expected):
    assert pascal_case_identifier(text) == expected


# --- pascal_case_identifier: digit-leading guard on the FINAL joined string ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("123abc", "_123abc"),
        ("123", "_123"),
        ("3D Viewer", "_3dViewer"),
    ],
)
def test_pascal_case_identifier_prefixes_underscore_when_digit_leading(text, expected):
    assert pascal_case_identifier(text) == expected
    assert pascal_case_identifier(text).isidentifier()


@pytest.mark.unit
def test_pascal_case_identifier_does_not_prefix_when_not_digit_leading():
    assert not pascal_case_identifier("abc123").startswith("_")


# --- pascal_case_identifier: avoids the slugify-then-resplit trap ---

@pytest.mark.unit
def test_pascal_case_identifier_avoids_slugify_resplit_trap():
    # Regression test for the core bug: building a PascalCase name by calling
    # slugify() and then splitting the result on "_" silently drops
    # slugify()'s own digit-leading guard, because "3d".capitalize() == "3d"
    # (no letter to capitalize) and the empty string from the leading "_"
    # vanishes on join. slugify("3D Model Sync") == "_3d_model_sync", and
    # "".join(w.capitalize() for w in "_3d_model_sync".split("_")) ==
    # "3dModelSync" - NOT a valid identifier. pascal_case_identifier must
    # tokenize the raw text directly and guard the final joined result
    # instead, producing a valid identifier.
    broken = "".join(w.capitalize() for w in slugify("3D Model Sync").split("_"))
    assert not broken.isidentifier()  # documents the trap this function avoids

    result = pascal_case_identifier("3D Model Sync")
    assert result == "_3dModelSync"
    assert result.isidentifier()


# --- pascal_case_identifier: general non-alphanumeric punctuation ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "text,expected",
    [
        ("api.v1", "ApiV1"),
        ("order/items", "OrderItems"),
        ("O'Brien Resource", "OBrienResource"),
        ("3-Way Merge", "_3WayMerge"),
    ],
)
def test_pascal_case_identifier_handles_general_punctuation(text, expected):
    result = pascal_case_identifier(text)
    assert result == expected
    assert result.isidentifier()


# --- pascal_case_identifier: fully-empty raises, mirroring slugify() ---

@pytest.mark.unit
@pytest.mark.parametrize("text", ["", "   ", "!!!", "___", "---", "..."])
def test_pascal_case_identifier_raises_when_no_usable_characters(text):
    with pytest.raises(ValueError, match="no usable characters"):
        pascal_case_identifier(text)
