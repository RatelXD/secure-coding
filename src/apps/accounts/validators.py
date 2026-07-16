import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

USERNAME_PATTERN = r"^[a-z0-9_]{4,30}$"
_CANONICAL_USERNAME = re.compile(USERNAME_PATTERN, flags=re.ASCII)
validate_canonical_username = RegexValidator(
    regex=USERNAME_PATTERN,
    message="Username must contain 4-30 lowercase ASCII letters, digits, or underscores.",
    code="invalid_username",
)


def canonicalize_username(value: str) -> str:
    """Return the sole persisted representation used for username uniqueness."""
    if not isinstance(value, str):
        raise ValidationError("Username must be text.", code="invalid_username")

    canonical = value.strip().lower()
    if _CANONICAL_USERNAME.fullmatch(canonical) is None:
        raise ValidationError(
            "Username must contain 4-30 lowercase ASCII letters, digits, or underscores.",
            code="invalid_username",
        )
    return canonical
