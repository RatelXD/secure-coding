from django.db import migrations


POSTGRES_FORWARD = (
    """
CREATE OR REPLACE FUNCTION moderation_reject_management_history_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'management audit and release history are append-only';
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER moderation_adminaudit_append_only
BEFORE UPDATE OR DELETE ON moderation_adminaudit
FOR EACH ROW EXECUTE FUNCTION moderation_reject_management_history_mutation();
""",
    """
CREATE TRIGGER moderation_sanctionrelease_append_only
BEFORE UPDATE OR DELETE ON moderation_sanctionrelease
FOR EACH ROW EXECUTE FUNCTION moderation_reject_management_history_mutation();
""",
)
POSTGRES_REVERSE = (
    "DROP TRIGGER IF EXISTS moderation_sanctionrelease_append_only ON moderation_sanctionrelease;",
    "DROP TRIGGER IF EXISTS moderation_adminaudit_append_only ON moderation_adminaudit;",
    "DROP FUNCTION IF EXISTS moderation_reject_management_history_mutation();",
)
SQLITE_FORWARD = (
    """
CREATE TRIGGER moderation_adminaudit_update_frozen BEFORE UPDATE ON moderation_adminaudit
BEGIN SELECT RAISE(ABORT, 'management audit is append-only'); END;
""",
    """
CREATE TRIGGER moderation_adminaudit_delete_frozen BEFORE DELETE ON moderation_adminaudit
BEGIN SELECT RAISE(ABORT, 'management audit is append-only'); END;
""",
    """
CREATE TRIGGER moderation_sanctionrelease_update_frozen BEFORE UPDATE ON moderation_sanctionrelease
BEGIN SELECT RAISE(ABORT, 'sanction release is append-only'); END;
""",
    """
CREATE TRIGGER moderation_sanctionrelease_delete_frozen BEFORE DELETE ON moderation_sanctionrelease
BEGIN SELECT RAISE(ABORT, 'sanction release is append-only'); END;
""",
)
SQLITE_REVERSE = tuple(
    f"DROP TRIGGER IF EXISTS {name};"
    for name in (
        "moderation_adminaudit_update_frozen",
        "moderation_adminaudit_delete_frozen",
        "moderation_sanctionrelease_update_frozen",
        "moderation_sanctionrelease_delete_frozen",
    )
)


def _execute(schema_editor, postgres_sql, sqlite_sql):
    vendor = schema_editor.connection.vendor
    statements = postgres_sql if vendor == "postgresql" else sqlite_sql if vendor == "sqlite" else None
    if statements is None:
        raise RuntimeError(f"unsupported database for management authority: {vendor}")
    for statement in statements:
        schema_editor.execute(statement)


def forward(apps, schema_editor):
    _execute(schema_editor, POSTGRES_FORWARD, SQLITE_FORWARD)


def reverse(apps, schema_editor):
    _execute(schema_editor, POSTGRES_REVERSE, SQLITE_REVERSE)


class Migration(migrations.Migration):
    dependencies = [("moderation", "0003_adminaudit_adminscopegrant_sanctionrelease_and_more")]
    operations = [migrations.RunPython(forward, reverse)]
