# Data Analytics Agent (demo)

An AI agent that answers questions about a retail sales database in plain English. It generates the SQL itself, runs it safely (read-only), self-corrects on errors, explains the results in plain language, and suggests a chart.

## What's inside

| File | Role |
|------|------|
| `database.py` | Builds `retail.db` (SQLite) with stores, products, employees, and ~8,000 sales rows. Read-only query access. |
| `llm.py` | Swappable LLM clients (Gemini / Groq / Ollama / OpenAI / OpenRouter / DeepSeek) via the OpenAI-compatible API. |
| `agent.py` | The agent: natural language -> SQL, safety validation, auto-fix on errors, chart recommendation, executive summary. |
| `app.py` | Streamlit chat UI with result table, SQL viewer, and interactive Plotly chart. |

## The agent pipeline

1. User asks a question → the LLM produces SQL (locked to the injected schema).
2. SQL is validated (SELECT-only, single statement, no dangerous keywords).
3. Query runs read-only with a row cap; if it errors, the agent fixes it and retries once.
4. The LLM writes a plain-English executive summary.
5. The LLM suggests a chart type (bar/line/pie/scatter) rendered with Plotly.

## Free LLM options (no credit card)

- **Gemini** — free key at [aistudio.google.com](https://aistudio.google.com). Pick `gemini` in the sidebar.
- **Groq** — free key at [console.groq.com](https://console.groq.com).
- **Ollama** — 100% local: `ollama pull llama3.2`, then pick `ollama` (no key).

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate        # PowerShell: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501).

## Example questions to try

- Which branches were the top 3 by revenue last month?
- What is the total revenue per product category this year?
- Show me the monthly revenue trend for 2025.
- Which products have the highest quantity sold?
- What share of total revenue came from each store?