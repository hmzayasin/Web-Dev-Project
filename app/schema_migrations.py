from sqlalchemy import inspect, text


def upgrade_schema(engine):
    """Apply additive changes needed by databases created before current features."""
    additions = {
        "user": {
            "cv_upload_version": "INTEGER NOT NULL DEFAULT 0",
        },
        "vacancy": {
            "version": "INTEGER NOT NULL DEFAULT 1",
            "closing_date": "DATE",
            "removal_reason": "TEXT",
            "removed_at": "DATETIME",
            "closing_date": "DATE",                       # J: R2 closing date
            "version": "INTEGER NOT NULL DEFAULT 1",      # J: optimistic locking
        },
    }

    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    ))
                    existing.add(column_name)
