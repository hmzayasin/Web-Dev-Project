from sqlalchemy import create_engine, inspect, text

from app.schema_migrations import upgrade_schema


def test_upgrade_adds_moderation_columns_to_existing_vacancy_table():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE vacancy (id INTEGER PRIMARY KEY, title VARCHAR(140) NOT NULL)"
            ))
            connection.execute(text("INSERT INTO vacancy (id, title) VALUES (1, 'Existing role')"))
            connection.execute(text("CREATE TABLE user (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO user (id) VALUES (1)"))

        upgrade_schema(engine)
        upgrade_schema(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("vacancy")}
        assert {"removal_reason", "removed_at"} <= columns
        user_columns = {column["name"] for column in inspect(engine).get_columns("user")}
        assert "cv_upload_version" in user_columns
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT title, removal_reason, removed_at FROM vacancy WHERE id = 1")
            ).one()
            upload_version = connection.execute(
                text("SELECT cv_upload_version FROM user WHERE id = 1")
            ).scalar_one()
        assert row == ("Existing role", None, None)
        assert upload_version == 0
    finally:
        engine.dispose()
