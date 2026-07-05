import re
import sqlite3

import pandas as pd


class SQLiteImporter:

    def __init__(self, database_path):
        self.database_path = database_path

    def load(self, table_name):
        self._validate_table_name(table_name)

        conn = sqlite3.connect(self.database_path)

        try:
            query = f'SELECT * FROM "{table_name}"'
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()

    def _validate_table_name(self, table_name):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError(f"Invalid SQLite table name: {table_name}")
