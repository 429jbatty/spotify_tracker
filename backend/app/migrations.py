from sqlalchemy import Engine, text


def _is_sqlite_engine(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def _table_columns(engine: Engine, table_name: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in rows}


def migrate_album_artwork_columns(engine: Engine) -> None:
    if not _is_sqlite_engine(engine):
        return

    columns = _table_columns(engine, "albums")
    if not columns:
        return

    with engine.begin() as connection:
        if "remote_image_url" not in columns:
            connection.execute(text("ALTER TABLE albums ADD COLUMN remote_image_url TEXT"))
            columns.add("remote_image_url")

        if "local_image_path" not in columns:
            connection.execute(text("ALTER TABLE albums ADD COLUMN local_image_path TEXT"))
            columns.add("local_image_path")

        connection.execute(
            text(
                """
                UPDATE albums
                SET remote_image_url = image_url
                WHERE (remote_image_url IS NULL OR remote_image_url = '')
                  AND image_url IS NOT NULL
                  AND image_url != ''
                """
            )
        )


def run_sqlite_migrations(engine: Engine) -> None:
    migrate_album_artwork_columns(engine)
