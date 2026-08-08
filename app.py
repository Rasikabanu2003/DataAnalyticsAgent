import os

import pandas as pd
import plotly.express as px
import streamlit as st

from agent import Agent
from database import get_schema_markdown, init_db
from db_source import DbSource
from llm import LLMClient, PROVIDERS

from dotenv import load_dotenv

load_dotenv()

EXAMPLE_QUESTIONS = [
    "Which branches were the top 3 by revenue last month?",
    "What is the total revenue per product category this year?",
    "Show me the monthly revenue trend for 2025.",
    "Which products have the highest quantity sold?",
    "What share of total revenue came from each store?",
]

st.set_page_config(page_title="Data Analytics Agent", page_icon=":bar_chart:", layout="wide")
init_db()
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    a[href*="github.com"] {display: none !important;}
    #GithubIcon {display: none !important;}
    .viewerBadge_container__1QSob,
    .styles_viewerBadge__1yB5_,
    .viewerBadge_link__1S137,
    .viewerBadge_text__1JaDK {display: none !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


def make_client():
    provider = st.session_state.provider
    spec = PROVIDERS[provider]
    api_key = st.session_state.get("api_key") or (os.environ.get("API_KEY") or "")
    model = st.session_state.get("model") or spec["default_model"]
    base_url = st.session_state.get("base_url") or spec["base_url"]
    return LLMClient(provider, api_key=api_key, model=model, base_url=base_url)


def make_source():
    source = st.session_state.get("source")
    if source is not None:
        return source
    return None


def effective_schema():
    source = make_source()
    return source.schema_markdown() if source is not None else get_schema_markdown()


def render_chart(chart_type, x, y, title, df):
    if df.empty or chart_type == "none":
        return
    if chart_type == "pie":
        fig = px.pie(df, names=x, values=y, title=title)
    elif chart_type == "line":
        fig = px.line(df, x=x, y=y, title=title, markers=True)
    elif chart_type == "scatter":
        fig = px.scatter(df, x=x, y=y, title=title)
    else:
        fig = px.bar(df, x=x, y=y, title=title)
    st.plotly_chart(fig, use_container_width=True)


with st.sidebar:
    st.header("Configuration")
    provider = st.selectbox("LLM provider", list(PROVIDERS.keys()), index=list(PROVIDERS).index("groq"))
    spec = PROVIDERS[provider]
    st.caption(spec["hint"])
    if spec["needs_key"]:
        api_key = st.text_input(
            "API key",
            type="password",
            value=os.environ.get("API_KEY", ""),
            help="Saved to your OS env, or type it here for this session.",
        )
    else:
        api_key = ""
        st.info("No API key needed — make sure Ollama is running.")
    model = st.text_input("Model (optional)", value="")
    base_url = st.text_input("Base URL (optional)", value="")
    if st.button("Start new conversation"):
        st.session_state["messages"] = []
        st.rerun()

    st.divider()
    st.subheader("Database")
    conn_str = st.text_input(
        "Connection string",
        value=st.session_state.get("conn_str", ""),
        help=(
            "SQLAlchemy-style URL. Examples:\n"
            "postgresql://user:pass@host:5432/dbname\n"
            "mysql+pymysql://user:pass@host:3306/dbname\n"
            "mssql+pymssql://user:pass@host:1433/dbname\n"
            "sqlite:///C:/path/to/database.db\n"
            "or just a file path like C:/data/my.db"
        ),
    )
    if st.button("Connect to this database"):
        url = conn_str.strip()
        if not url:
            st.session_state.pop("source", None)
            st.session_state["conn_str"] = ""
            st.success("Using the bundled demo database.")
        else:
            try:
                source = DbSource(url)
                tables = source.schema_markdown()
                st.session_state["source"] = source
                st.session_state["conn_str"] = url
                st.success(f"Connected: {source.dialect} ({len(tables.splitlines())} tables)")
            except Exception as e:
                st.session_state.pop("source", None)
                st.error(f"Connection failed: {e}")

    if make_source() is not None:
        st.success(f"Active source: **{make_source().dialect}**")

    st.divider()
    st.subheader("Schema")
    st.code(effective_schema(), language="markdown")

st.session_state["provider"] = provider
st.session_state["api_key"] = api_key
st.session_state["model"] = model
st.session_state["base_url"] = base_url

st.title(":bar_chart: Data Analytics Agent")
st.write("Ask questions in plain English about your database — the agent writes and runs the SQL, then explains and charts the results.")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

st.markdown("**Try an example:**")
cols = st.columns(len(EXAMPLE_QUESTIONS))
for i, q in enumerate(EXAMPLE_QUESTIONS):
    if cols[i].button(q, key=f"ex{i}"):
        st.session_state["pending_question"] = q
        st.rerun()
st.divider()

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("df") is not None:
            with st.expander("View query"):
                st.code(msg["sql"], language="sql")
            st.dataframe(msg["df"], use_container_width=True)
            render_chart(
                msg.get("chart", "none"),
                msg.get("x", ""),
                msg.get("y", ""),
                msg.get("title", ""),
                msg["df"],
            )

user_question = st.chat_input("Ask about your sales data...")

if user_question is None and "pending_question" in st.session_state:
    user_question = st.session_state.pop("pending_question", None)

if user_question:
    st.chat_message("user").markdown(user_question)
    st.session_state["messages"].append({"role": "user", "content": user_question})

    with st.chat_message("assistant"):
        try:
            agent = Agent(make_client(), source=make_source())
            status = st.status("Running analysis...", expanded=True)
            result = agent.analyze(
                user_question,
                on_step=lambda s: status.write(s),
            )
            status.update(label="Done", state="complete", expanded=False)

            st.markdown(f"**{result['summary']}**")
            with st.expander("SQL generated by the agent"):
                st.code(result["sql"], language="sql")
            df = result["dataframe"]
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                render_chart(result["chart"], result["x"], result["y"], result["title"], df)

            st.session_state["messages"].append(
                {
                    "role": "assistant",
                    "content": result["summary"],
                    "sql": result["sql"],
                    "df": df if not df.empty else None,
                    "chart": result["chart"],
                    "x": result["x"],
                    "y": result["y"],
                    "title": result["title"],
                }
            )
        except Exception as e:
            st.error(f"Something went wrong: {e}")