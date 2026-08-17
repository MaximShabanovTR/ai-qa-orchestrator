import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug:
        raise ValueError(f"slugify: {text!r} has no usable characters to build an identifier from")
    if slug[0].isdigit():
        return f"_{slug}"
    return slug
