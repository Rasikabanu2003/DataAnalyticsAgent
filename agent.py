import re

import pandas as pd

from database import get_schema_markdown, query

MAX_ROWS = 500
FORBIDDEN_KEYWORDS = [
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "attach",
    "detach",
    "pragma",
    "vacuum",
    "transaction",
    "truncate",
    "grant",
    "reindex",
    "begin",
    "commit",
    "rollback",
]

SQL_SYSTEM_PROMPT = """You are a senior data analyst who writes SQL for a {dialect} database.
Database schema:
{schema}

Rules:
- Use {dialect}-specific syntax and functions only. Hint: {dialect_hints}
- You must only SELECT data. NEVER write INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or any other modifying statement.
- Only reference tables and columns present in the schema; never invent them.
- Alias aggregate columns clearly (e.g. AS total_revenue, AS order_count).
- Limit results to a sensible number of rows when relevant.
- Return ONLY JSON with a single key "sql" containing one SELECT statement.

User question: {question}"""

FIX_SYSTEM_PROMPT = """You are an expert {dialect} SQL debugger.
The user asked a question and the generated query raised an error.
Fix the SQL query so it runs correctly against this schema:

{schema}

The query failed with this error:
{error}

Rules:
- Return ONLY JSON with a single key "sql" containing the corrected SELECT statement.
- Use only tables/columns present in the schema.
- Use {dialect}-specific syntax and functions only.
- Keep the same intent as the original question: {question}"""

SUMMARIZE_SYSTEM_PROMPT = """You are a data analyst explaining results to a non-technical executive.
User question: {question}

The query that ran was:
{sql}

Rows returned (first {limit} shown; may be truncated):
{rows}

Explain the answer clearly and concisely.
Mention the key numbers and what they mean for the business.
Do NOT include SQL in your explanation.
Return ONLY JSON with a single key "summary" containing a conversational explanation
(e.g. "Last month's top-selling store was X with $Y in revenue.")."""

CHART_SYSTEM_PROMPT = """You are a visualization expert.
Based on the user's question and the query result, decide if a chart would help and which kind.

User question: {question}
Query: {sql}
Result columns: {columns}
Result preview (first {limit} rows):
{rows}

Choose from chart types: "bar", "line", "pie", "scatter", or "none".
- Use "bar" for category vs value comparisons.
- Use "line" for trends over time (e.g. dates).
- Use "pie" for shares of a total by category.
- Use "scatter" for two numerical columns.
If the result is a single number or a few values where a chart adds nothing, use "none".

Return ONLY JSON with keys:
{{"type": "bar|line|pie|scatter|none",
 "x": "name of column for x-axis",
 "y": "name of numeric column for y-axis",
 "title": "short chart title"}}"""


def _validate_sql(sql):
    sql = sql.strip().rstrip(";")
    lowered = " ".join(sql.lower().split())
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            raise ValueError(f"Forbidden keyword '{kw}' in query.")
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Query must start with SELECT (or WITH).")
    if ";" in lowered:
        raise ValueError("Multiple statements are not allowed.")
    return sql


class Agent:
    def __init__(self, llm, source=None):
        self.llm = llm
        self.source = source
        self.dialect = "sqlite" if source is None else source.dialect
        self.schema = get_schema_markdown() if source is None else source.schema_markdown()
        from db_source import DIALECT_HINTS
        self.dialect_hints = DIALECT_HINTS.get(self.dialect, "standard SQL")

    def analyze(self, question, on_step=None):
        def step(msg):
            if on_step:
                on_step(msg)

        step("Generating SQL from your question...")
        sql = self._generate_sql(question)
        step(f"Validated query: {sql}")

        df = self._run_with_retries(question, sql, step)
        step("Explaining the results...")

        chart = {}
        try:
            chart = self._suggest_chart(question, sql, df)
        except Exception as e:
            step(f"Chart suggestion skipped ({e})")

        summary = self._summarize(question, sql, df)
        return {
            "sql": sql,
            "dataframe": df,
            "chart": (chart or {}).get("type", "none"),
            "title": (chart or {}).get("title", ""),
            "x": (chart or {}).get("x", df.columns[0] if len(df.columns) else ""),
            "y": (chart or {}).get("y", ""),
            "summary": summary,
        }

    def _generate_sql(self, question):
        result = self.llm.complete_json(
            SQL_SYSTEM_PROMPT.format(
                question=question,
                schema=self.schema,
                dialect=self.dialect,
                dialect_hints=self.dialect_hints,
            ),
            "Generate the SQL query for this question.",
        )
        return _validate_sql(result["sql"])

    def _run(self, sql):
        if self.source is not None:
            return self.source.query(sql)
        rows = query(sql)
        if len(rows) > MAX_ROWS:
            rows = rows[:MAX_ROWS]
        df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
        return df

    def _run_with_retries(self, question, sql, step):
        for attempt in range(2):
            try:
                return self._run(sql)
            except Exception as e:
                if attempt == 0:
                    step(f"Query failed ({e}). Asking the model to fix it...")
                    sql = self._fix_sql(question, sql, str(e))
                else:
                    raise
        raise RuntimeError("Query could not be executed after retry.")

    def _run_with_error(self, sql):
        try:
            return self._run(sql), None
        except Exception as e:
            return None, str(e)

    def _fix_sql(self, question, bad_sql, error):
        result = self.llm.complete_json(
            FIX_SYSTEM_PROMPT.format(
                question=question,
                error=error,
                schema=self.schema,
                dialect=self.dialect,
            ),
            "Fix the query.",
        )
        return _validate_sql(result["sql"])

    def _suggest_chart(self, question, sql, df):
        if df.empty:
            return {"type": "none"}
        limit = min(len(df), 8)
        sampled = df.head(limit).to_string()
        result = self.llm.complete_json(
            CHART_SYSTEM_PROMPT.format(
                question=question,
                sql=sql,
                columns=", ".join(df.columns),
                rows=sampled,
                limit=limit,
            ),
            "Choose the chart.",
        )
        return result

    def _summarize(self, question, sql, df):
        limit = min(len(df), 8)
        sampled = df.head(limit).to_string(index=False)
        result = self.llm.complete_json(
            SUMMARIZE_SYSTEM_PROMPT.format(question=question, sql=sql, rows=sampled, limit=limit),
            "Summarize the results.",
        )
        return result.get("summary", "Here are the results above.")