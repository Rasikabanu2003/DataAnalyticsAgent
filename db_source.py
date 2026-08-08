import pandas as pd
from sqlalchemy import create_engine, inspect, text

MAX_ROWS = 500

DIALECT_HINTS = {
    "sqlite": "e.g. strftime('%Y-%m', date_col), DATE(date_col)",
    "postgresql": "e.g. to_char(date_col, 'YYYY-MM'), date_trunc('month', date_col)",
    "mysql": "e.g. DATE_FORMAT(date_col, '%Y-%m'), DATE(date_col)",
    "mssql": "e.g. FORMAT(date_col, 'yyyy-MM')",
}


def normalize_url(url):
    url = url.strip()
    if url and "://" not in url:
        url = "sqlite:///" + url.replace("\\", "/")
    return url


class DbSource:
    def __init__(self, url):
        self.url = normalize_url(url)
        self.engine = create_engine(self.url)
        self.dialect = self.engine.dialect.name

    def schema_markdown(self):
        with self.engine.connect() as conn:
            insp = inspect(conn)
            lines = []
            for table in insp.get_table_names():
                columns = [
                    f"{c['name']} ({c['type']})" for c in insp.get_columns(table)
                ]
                lines.append(f"- **{table}:** " + ", ".join(columns))
        return "\n".join(lines)

    def query(self, sql):
        with self.engine.connect() as conn:
            if self.dialect == "postgresql":
                conn.execute(text("SET TRANSACTION READ ONLY"))
            elif self.dialect == "mysql":
                conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = [tuple(r) for r in result.fetchmany(MAX_ROWS + 1)][:MAX_ROWS]
            if not cols:
                return pd.DataFrame()
            return pd.DataFrame(rows, columns=cols)