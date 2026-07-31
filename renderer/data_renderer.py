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
    for profile in data_profiles:
        lines.extend(_render_profile(profile))
    content = "\n".join(lines) + "\n"
    return [
        _render_init(conventions),
        CodeArtifact(
            path=f"{conventions.data_dir}/profiles.py",
            content=content,
            kind=ArtifactKind.DATA_FACTORY,
            provenance=[profile.id for profile in data_profiles],
        ),
    ]


def _render_init(conventions: RendererConventions) -> CodeArtifact:
    return CodeArtifact(
        path=f"{conventions.data_dir}/__init__.py",
        content="",
        kind=ArtifactKind.DATA_FACTORY,
    )


def _constant_name(profile: DataProfile) -> str:
    return slugify(profile.name).upper()


def _generator_name(profile: DataProfile) -> str:
    return f"generate_{slugify(profile.name)}"


def _render_profile(profile: DataProfile) -> list[str]:
    if profile.literal_value is not None:
        return _render_literal_constant(profile)
    return _render_generator_function(profile)


def _render_literal_constant(profile: DataProfile) -> list[str]:
    return [f"{_constant_name(profile)} = {repr(profile.literal_value)}", ""]


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


def _render_generator_function(profile: DataProfile) -> list[str]:
    if profile.category is not DataCategory.UNSUPPORTED and not (profile.constraints and profile.constraints.pattern):
        lines = []
        lines.append(f"def {_generator_name(profile)}():")
        lines.append(f"    return {_GENERATORS[profile.category](profile)}")
        lines.append("")
        return lines
    else:
        raise NotImplementedError("no deterministic generator for this type")