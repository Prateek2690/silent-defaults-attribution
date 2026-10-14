"""Thin SQL engine abstraction: DuckDB if installed, else sqlite3 (for validation only)."""
import pandas as pd
try:
    import duckdb  # type: ignore
    HAVE_DUCKDB = True
except ImportError:  # pragma: no cover
    import sqlite3
    HAVE_DUCKDB = False


class Engine:
    def __init__(self):
        self.name = "duckdb" if HAVE_DUCKDB else "sqlite3"
        self.con = duckdb.connect() if HAVE_DUCKDB else sqlite3.connect(":memory:")

    def load(self, name: str, df: pd.DataFrame):
        if HAVE_DUCKDB:
            self.con.execute(f"DROP TABLE IF EXISTS {name}")
            self.con.register("_tmp_df", df)
            self.con.execute(f"CREATE TABLE {name} AS SELECT * FROM _tmp_df")
            self.con.unregister("_tmp_df")
        else:
            df.to_sql(name, self.con, index=False, if_exists="replace")

    def execute(self, sql: str):
        if HAVE_DUCKDB:
            self.con.execute(sql)
        else:
            self.con.executescript(sql)

    def query(self, sql: str) -> pd.DataFrame:
        if HAVE_DUCKDB:
            return self.con.execute(sql).df()
        return pd.read_sql_query(sql, self.con)
