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


class PasswordBoundsValidator:
    """Enforce the fixed Cycle 1 password bounds for every Django entrypoint."""

    min_length = 12
    max_length = 128

    def validate(self, password: str, user: object | None = None) -> None:
        if "\x00" in password:
            raise ValidationError("Password contains an invalid character.", code="password_nul")
        if len(password) < self.min_length:
            raise ValidationError(
                f"Password must contain at least {self.min_length} characters.",
                code="password_too_short",
            )
        if len(password) > self.max_length:
            raise ValidationError(
                f"Password must contain at most {self.max_length} characters.",
                code="password_too_long",
            )

    def get_help_text(self) -> str:
        return "Your password must contain 12 to 128 characters and no NUL character."
