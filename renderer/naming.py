import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"element_{slug}" if slug else "element"
    return slug
