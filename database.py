import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retail.db")

STORES = [
    ("Manhattan Flagship", "New York", "USA"),
    ("Brooklyn Heights", "New York", "USA"),
    ("Los Angeles Central", "Los Angeles", "USA"),
    ("Bay Area Store", "San Francisco", "USA"),
    ("West Coast Hub", "Seattle", "USA"),
    ("Chicago Loop", "Chicago", "USA"),
    ("Miami Beach", "Miami", "USA"),
    ("Austin Downtown", "Austin", "USA"),
]

PRODUCTS = [
    ("Wireless Mouse Pro", "Electronics", 39.99),
    ("Mechanical Keyboard", "Electronics", 129.99),
    ("USB-C Hub", "Electronics", 39.99),
    ("Noise-Cancelling Headphones", "Electronics", 89.99),
    ("Webcam HD", "Electronics", 59.99),
    ("Standing Desk", "Furniture", 349.00),
    ("Ergonomic Chair", "Furniture", 289.00),
    ("Desk Lamp LED", "Furniture", 29.99),
    ("Bookshelf", "Furniture", 129.00),
    ("Yoga Mat", "Sports", 25.00),
    ("Resistance Bands", "Sports", 19.99),
    ("Dumbbell Set", "Sports", 89.99),
    ("Jump Rope", "Sports", 12.99),
    ("Laptop Sleeve", "Accessories", 24.99),
    ("Laptop Stand", "Accessories", 34.99),
    ("Blue-Light Glasses", "Accessories", 49.99),
    ("Desk Organizer", "Accessories", 22.99),
    ("Python Cookbook", "Books", 39.99),
    ("Data Science 101", "Books", 44.99),
    ("SQL Cookbook", "Books", 35.99),
]

PRODUCT_PRICES = {name: price for name, _, price in PRODUCTS}
PRODUCT_IDS = {name: i + 1 for i, (name, _, _) in enumerate(PRODUCTS)}

STORE_WEIGHTS = [0.25, 0.12, 0.15, 0.12, 0.10, 0.10, 0.08, 0.08]


def _connect_ro():
    uri = Path(DB_PATH).as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    rng = random.Random(42)
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stores (
            store_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS employees (
            employee_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            store_id INTEGER NOT NULL REFERENCES stores(store_id),
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales (
            sale_id INTEGER PRIMARY KEY,
            store_id INTEGER NOT NULL REFERENCES stores(store_id),
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
            sale_date TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL
        );
        """
    )
    conn.commit()

    if conn.execute("SELECT COUNT(*) AS c FROM stores").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO stores (name, city, country) VALUES (?, ?, ?)", STORES
        )
        conn.commit()

    if conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO products (name, category, price) VALUES (?, ?, ?)", PRODUCTS
        )
        conn.commit()

    if conn.execute("SELECT COUNT(*) AS c FROM employees").fetchone()["c"] == 0:
        emp_rows = []
        eid = 1
        for sid in range(1, len(STORES) + 1):
            for role in ("manager", "cashier", "cashier"):
                emp_rows.append((eid, f"{role.title()} {eid}", sid, role))
                eid += 1
        conn.executemany(
            "INSERT INTO employees (employee_id, name, store_id, role) VALUES (?, ?, ?, ?)",
            emp_rows,
        )
        conn.commit()

    if conn.execute("SELECT COUNT(*) AS c FROM sales").fetchone()["c"] == 0:
        start = date(2024, 1, 1)
        end = date(2026, 8, 1)
        n_days = (end - start).days
        rows = []
        name_by_id = {pid: name for name, pid in PRODUCT_IDS.items()}
        for _ in range(8000):
            store_id = rng.choices(range(1, len(STORES) + 1), weights=STORE_WEIGHTS, k=1)[0]
            product_id = rng.randint(1, len(PRODUCTS))
            price = PRODUCT_PRICES[name_by_id[product_id]]
            sale_date = start + timedelta(days=rng.randint(0, n_days))
            quantity = rng.randint(1, 5)
            employee_id = (store_id - 1) * 3 + rng.randint(1, 3)
            rows.append(
                (store_id, product_id, employee_id, sale_date.isoformat(), quantity, price)
            )
        conn.executemany(
            "INSERT INTO sales (store_id, product_id, employee_id, sale_date, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    conn.close()


def query(sql, params=()):
    conn = _connect_ro()
    try:
        conn.execute("PRAGMA query_only = ON")
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def get_schema_markdown():
    conn = _connect_ro()
    try:
        tables = {}
        names = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for name in names:
            columns = ", ".join(
                f"{r['name']} ({r['type']})"
                for r in conn.execute(f"PRAGMA table_info({name})").fetchall()
            )
            tables[name] = columns
    finally:
        conn.close()
    return "\n".join(f"- **{t}:** {cols}" for t, cols in tables.items())