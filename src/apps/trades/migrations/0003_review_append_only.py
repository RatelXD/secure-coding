from django.db import migrations


POSTGRES_FORWARD = (
    """
CREATE OR REPLACE FUNCTION trades_reject_review_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'reviews and visibility actions are append-only';
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER trades_review_append_only
BEFORE UPDATE OR DELETE ON trades_review
FOR EACH ROW EXECUTE FUNCTION trades_reject_review_mutation();
""",
    """
CREATE TRIGGER trades_review_visibility_append_only
BEFORE UPDATE OR DELETE ON trades_reviewvisibilityaction
FOR EACH ROW EXECUTE FUNCTION trades_reject_review_mutation();
""",
)
POSTGRES_REVERSE = (
    "DROP TRIGGER IF EXISTS trades_review_visibility_append_only ON trades_reviewvisibilityaction;",
    "DROP TRIGGER IF EXISTS trades_review_append_only ON trades_review;",
    "DROP FUNCTION IF EXISTS trades_reject_review_mutation();",
)
SQLITE_FORWARD = (
    """
CREATE TRIGGER trades_review_update_frozen BEFORE UPDATE ON trades_review
BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END;
""",
    """
CREATE TRIGGER trades_review_delete_frozen BEFORE DELETE ON trades_review
BEGIN SELECT RAISE(ABORT, 'reviews are append-only'); END;
""",
    """
CREATE TRIGGER trades_review_visibility_update_frozen BEFORE UPDATE ON trades_reviewvisibilityaction
BEGIN SELECT RAISE(ABORT, 'review visibility actions are append-only'); END;
""",
    """
CREATE TRIGGER trades_review_visibility_delete_frozen BEFORE DELETE ON trades_reviewvisibilityaction
BEGIN SELECT RAISE(ABORT, 'review visibility actions are append-only'); END;
""",
)
SQLITE_REVERSE = tuple(
    f"DROP TRIGGER IF EXISTS {name};"
    for name in (
        "trades_review_update_frozen",
        "trades_review_delete_frozen",
        "trades_review_visibility_update_frozen",
        "trades_review_visibility_delete_frozen",
    )
)


def _execute(schema_editor, postgres_sql, sqlite_sql):
    vendor = schema_editor.connection.vendor
    statements = postgres_sql if vendor == "postgresql" else sqlite_sql if vendor == "sqlite" else None
    if statements is None:
        raise RuntimeError(f"unsupported database for review authority: {vendor}")
    for statement in statements:
        schema_editor.execute(statement)


def forward(apps, schema_editor):
    _execute(schema_editor, POSTGRES_FORWARD, SQLITE_FORWARD)


def reverse(apps, schema_editor):
    _execute(schema_editor, POSTGRES_REVERSE, SQLITE_REVERSE)


class Migration(migrations.Migration):
    dependencies = [("trades", "0002_review_reviewvisibilityaction_and_more")]
    operations = [migrations.RunPython(forward, reverse)]
