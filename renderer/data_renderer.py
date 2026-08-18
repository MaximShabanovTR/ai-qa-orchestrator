from typing import Callable

from models.automation import DataCategory, DataProfile
from renderer.models import ArtifactKind, CodeArtifact, RendererConventions
from renderer.naming import slugify

_HEADER = [
    "import random",
    "import string",
    "from datetime import date, datetime, timedelta",
    "",
    "",
]


def render_data(
    data_profiles: list[DataProfile], conventions: RendererConventions
) -> list[CodeArtifact]:
    lines = list(_HEADER)
    has_gap = False
    for profile in data_profiles:
        profile_lines, is_gap = _render_profile(profile)
        lines.extend(profile_lines)
        has_gap = has_gap or is_gap
    content = "\n".join(lines) + "\n"
    return [
        _render_init(conventions),
        CodeArtifact(
            path=f"{conventions.data_dir}/profiles.py",
            content=content,
            kind=ArtifactKind.DATA_FACTORY,
            source="unsupported" if has_gap else "deterministic",
            provenance=[profile.id for profile in data_profiles],
        ),
    ]


def _render_init(conventions: RendererConventions) -> CodeArtifact:
    return CodeArtifact(
        path=f"{conventions.data_dir}/__init__.py",
        content="",
        kind=ArtifactKind.DATA_FACTORY,
    )


def constant_name(profile: DataProfile) -> str:
    return slugify(profile.name).upper()


def generator_name(profile: DataProfile) -> str:
    return f"generate_{slugify(profile.name)}"


def _render_profile(profile: DataProfile) -> tuple[list[str], bool]:
    """Returns (source_lines, is_honest_gap).

    is_honest_gap is True when the rendered generator function's body
    raises NotImplementedError when called, rather than returning a
    value - see _render_generator_function.
    """
    if profile.literal_value is not None:
        return _render_literal_constant(profile), False
    return _render_generator_function(profile)


def _render_literal_constant(profile: DataProfile) -> list[str]:
    return [f"{constant_name(profile)} = {repr(profile.literal_value)}", ""]


def _generate_text(profile: DataProfile) -> str:
    constraints = profile.constraints
    min_length = (
        constraints.min_length if constraints and constraints.min_length is not None else 5
    )
    max_length = (
        constraints.max_length if constraints and constraints.max_length is not None else 20
    )
    return (
        f'"".join(random.choices(string.ascii_letters, '
        f"k=random.randint({min_length}, {max_length})))"
    )


def _generate_number(profile: DataProfile) -> str:
    constraints = profile.constraints
    min_value = (
        constraints.min_value if constraints and constraints.min_value is not None else 0
    )
    max_value = (
        constraints.max_value if constraints and constraints.max_value is not None else 1000
    )
    return f"random.uniform({min_value}, {max_value})"


def _generate_boolean(profile: DataProfile) -> str:
    return "random.choice([True, False])"


def _generate_email(profile: DataProfile) -> str:
    return 'f"user{random.randint(0, 99999)}@example.com"'


def _generate_url(profile: DataProfile) -> str:
    return 'f"https://example.com/{random.randint(0, 99999)}"'


def _generate_date(profile: DataProfile) -> str:
    return "str(date.today() + timedelta(days=random.randint(-365, 365)))"


def _generate_datetime(profile: DataProfile) -> str:
    return "str(datetime.now() + timedelta(minutes=random.randint(-1000, 1000)))"


_GENERATORS: dict[DataCategory, Callable[[DataProfile], str]] = {
    DataCategory.TEXT: _generate_text,
    DataCategory.NUMBER: _generate_number,
    DataCategory.BOOLEAN: _generate_boolean,
    DataCategory.EMAIL: _generate_email,
    DataCategory.URL: _generate_url,
    DataCategory.DATE: _generate_date,
    DataCategory.DATETIME: _generate_datetime,
}


def _render_generator_function(profile: DataProfile) -> tuple[list[str], bool]:
    """Renders a generator function definition for `profile`.

    Two cases, both of which return normally - rendering source code must
    never raise (see .docs/architecture.md, "Generated framework has zero
    third-party runtime dependencies"): a single UNSUPPORTED-category or
    pattern-constrained profile must not abort the whole framework render.

    - Deterministic case: the function body returns a stdlib-generated
      value.
    - Honest-gap case (UNSUPPORTED category, or a pattern-constrained
      profile - stdlib genuinely cannot generate an arbitrary regex
      match): the function is still syntactically valid and importable,
      but its body raises NotImplementedError - the failure only surfaces
      if a generated test actually calls this specific generator, same
      tier as TestRenderer's Unsupported-step skip.
    """
    if profile.category is not DataCategory.UNSUPPORTED and not (profile.constraints and profile.constraints.pattern):
        lines = []
        lines.append(f"def {generator_name(profile)}():")
        lines.append(f"    return {_GENERATORS[profile.category](profile)}")
        lines.append("")
        return lines, False
    lines = []
    lines.append(f"def {generator_name(profile)}():")
    message = (
        f"no deterministic generator for {profile.name!r} "
        f"(category={profile.category.value})"
    )
    lines.append(f"    raise NotImplementedError({message!r})")
    lines.append("")
    return lines, True