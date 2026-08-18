import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug:
        raise ValueError(f"slugify: {text!r} has no usable characters to build an identifier from")
    if slug[0].isdigit():
        return f"_{slug}"
    return slug


def pascal_case_identifier(text: str) -> str:
    """Build a PascalCase Python identifier directly from raw text.

    Tokenizes ``text`` the same way ``slugify()`` does - runs of characters
    outside ``[a-zA-Z0-9]`` are treated as separators - then capitalizes and
    joins each token. The digit-leading guard is applied to the *final*
    joined PascalCase string, mirroring slugify()'s own guard.

    This must be used instead of slugify()-then-resplit-on-"_" for building
    PascalCase names: slugify() lowercases and may prefix a leading "_" to
    guard against a digit-leading result, but splitting that already-slugified
    string back on "_" and capitalizing each piece silently drops the guard
    again (e.g. "_3d_model_sync".split("_") -> ['', '3d', 'model', 'sync'];
    "3d".capitalize() is "3d" unchanged, and the empty string from the
    leading "_" vanishes on join). Tokenizing the raw input directly and
    guarding the final result avoids that trap entirely.
    """
    words = re.findall(r"[a-zA-Z0-9]+", text)
    if not words:
        raise ValueError(
            f"pascal_case_identifier: {text!r} has no usable characters to build an identifier from"
        )
    name = "".join(word.capitalize() for word in words)
    if name[0].isdigit():
        return f"_{name}"
    return name
