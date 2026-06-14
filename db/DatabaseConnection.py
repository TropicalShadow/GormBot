from typing import Any


class DatabaseConnection:
    def __init__(self, file_name: str, table_name: str) -> None:
        self.file_name = file_name
        self.table_name = table_name

    def __enter__(self, *args: object, **kwargs: object) -> Any:
        from sqlitedict import SqliteDict

        self.db = SqliteDict(
            self.file_name, autocommit=True, tablename=self.table_name
        )
        return self.db

    def __exit__(self, *args: object, **kwargs: object) -> None:
        self.db.close()
