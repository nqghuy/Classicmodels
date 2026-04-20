#!/usr/bin/env python3
"""ClassicModels REST API with a lightweight ORM-style data layer.

Run:
    python3 server.py

Open:
    http://localhost:8000
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
SQL_FILE = BASE_DIR / "mysqlsampledatabase.sql"
DB_FILE = BASE_DIR / "classicmodels.sqlite"
ENV_FILE = BASE_DIR / ".env"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


SCHEMAS: dict[str, list[str]] = {
    "productlines": ["productLine", "textDescription", "htmlDescription", "image"],
    "products": [
        "productCode",
        "productName",
        "productLine",
        "productScale",
        "productVendor",
        "productDescription",
        "quantityInStock",
        "buyPrice",
        "MSRP",
    ],
    "offices": [
        "officeCode",
        "city",
        "phone",
        "addressLine1",
        "addressLine2",
        "state",
        "country",
        "postalCode",
        "territory",
    ],
    "employees": [
        "employeeNumber",
        "lastName",
        "firstName",
        "extension",
        "email",
        "officeCode",
        "reportsTo",
        "jobTitle",
    ],
    "customers": [
        "customerNumber",
        "customerName",
        "contactLastName",
        "contactFirstName",
        "phone",
        "addressLine1",
        "addressLine2",
        "city",
        "state",
        "postalCode",
        "country",
        "salesRepEmployeeNumber",
        "creditLimit",
    ],
    "payments": ["customerNumber", "checkNumber", "paymentDate", "amount"],
    "orders": ["orderNumber", "orderDate", "requiredDate", "shippedDate", "status", "comments", "customerNumber"],
    "orderdetails": ["orderNumber", "productCode", "quantityOrdered", "priceEach", "orderLineNumber"],
}


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE productlines (
  productLine TEXT PRIMARY KEY,
  textDescription TEXT,
  htmlDescription TEXT,
  image BLOB
);

CREATE TABLE products (
  productCode TEXT PRIMARY KEY,
  productName TEXT NOT NULL,
  productLine TEXT NOT NULL,
  productScale TEXT NOT NULL,
  productVendor TEXT NOT NULL,
  productDescription TEXT NOT NULL,
  quantityInStock INTEGER NOT NULL,
  buyPrice REAL NOT NULL,
  MSRP REAL NOT NULL,
  FOREIGN KEY (productLine) REFERENCES productlines (productLine)
);

CREATE TABLE offices (
  officeCode TEXT PRIMARY KEY,
  city TEXT NOT NULL,
  phone TEXT NOT NULL,
  addressLine1 TEXT NOT NULL,
  addressLine2 TEXT,
  state TEXT,
  country TEXT NOT NULL,
  postalCode TEXT NOT NULL,
  territory TEXT NOT NULL
);

CREATE TABLE employees (
  employeeNumber INTEGER PRIMARY KEY,
  lastName TEXT NOT NULL,
  firstName TEXT NOT NULL,
  extension TEXT NOT NULL,
  email TEXT NOT NULL,
  officeCode TEXT NOT NULL,
  reportsTo INTEGER,
  jobTitle TEXT NOT NULL,
  FOREIGN KEY (reportsTo) REFERENCES employees (employeeNumber),
  FOREIGN KEY (officeCode) REFERENCES offices (officeCode)
);

CREATE TABLE customers (
  customerNumber INTEGER PRIMARY KEY,
  customerName TEXT NOT NULL,
  contactLastName TEXT NOT NULL,
  contactFirstName TEXT NOT NULL,
  phone TEXT NOT NULL,
  addressLine1 TEXT NOT NULL,
  addressLine2 TEXT,
  city TEXT NOT NULL,
  state TEXT,
  postalCode TEXT,
  country TEXT NOT NULL,
  salesRepEmployeeNumber INTEGER,
  creditLimit REAL,
  FOREIGN KEY (salesRepEmployeeNumber) REFERENCES employees (employeeNumber)
);

CREATE TABLE payments (
  customerNumber INTEGER NOT NULL,
  checkNumber TEXT NOT NULL,
  paymentDate TEXT NOT NULL,
  amount REAL NOT NULL,
  PRIMARY KEY (customerNumber, checkNumber),
  FOREIGN KEY (customerNumber) REFERENCES customers (customerNumber)
);

CREATE TABLE orders (
  orderNumber INTEGER PRIMARY KEY,
  orderDate TEXT NOT NULL,
  requiredDate TEXT NOT NULL,
  shippedDate TEXT,
  status TEXT NOT NULL,
  comments TEXT,
  customerNumber INTEGER NOT NULL,
  FOREIGN KEY (customerNumber) REFERENCES customers (customerNumber)
);

CREATE TABLE orderdetails (
  orderNumber INTEGER NOT NULL,
  productCode TEXT NOT NULL,
  quantityOrdered INTEGER NOT NULL,
  priceEach REAL NOT NULL,
  orderLineNumber INTEGER NOT NULL,
  PRIMARY KEY (orderNumber, productCode),
  FOREIGN KEY (orderNumber) REFERENCES orders (orderNumber),
  FOREIGN KEY (productCode) REFERENCES products (productCode)
);
"""


class Database:
    """Small connection manager used by ORM models and API reports."""

    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        with self.connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            return None if row is None else row[0]


db = Database(DB_FILE)


def load_local_env() -> None:
    """Load simple KEY=VALUE pairs from .env without requiring python-dotenv."""
    if not ENV_FILE.exists():
        return

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class Query:
    """Minimal query builder so endpoint code can use ORM-like model access."""

    def __init__(
        self,
        model: type["Model"],
        filters: list[str] | None = None,
        params: list[Any] | None = None,
        ordering: str | None = None,
        limit_count: int | None = None,
    ):
        self.model = model
        self.filters = filters or []
        self.params = params or []
        self.ordering = ordering
        self.limit_count = limit_count

    def where(self, condition: str, *params: Any) -> "Query":
        return Query(self.model, self.filters + [condition], self.params + list(params), self.ordering, self.limit_count)

    def order_by(self, expression: str) -> "Query":
        return Query(self.model, self.filters, self.params, expression, self.limit_count)

    def limit(self, count: int) -> "Query":
        return Query(self.model, self.filters, self.params, self.ordering, count)

    def all(self) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {self.model.table}"
        if self.filters:
            sql += " WHERE " + " AND ".join(f"({item})" for item in self.filters)
        if self.ordering:
            sql += f" ORDER BY {self.ordering}"
        if self.limit_count is not None:
            sql += " LIMIT ?"
            params = self.params + [self.limit_count]
        else:
            params = self.params
        return db.query(sql, params)

    def first(self) -> dict[str, Any] | None:
        rows = self.limit(1).all()
        return rows[0] if rows else None


class Model:
    table = ""
    pk = ""

    @classmethod
    def objects(cls) -> Query:
        return Query(cls)

    @classmethod
    def get(cls, pk: Any) -> dict[str, Any] | None:
        return cls.objects().where(f"{cls.pk} = ?", pk).first()


class Customer(Model):
    table = "customers"
    pk = "customerNumber"


class Order(Model):
    table = "orders"
    pk = "orderNumber"


class Product(Model):
    table = "products"
    pk = "productCode"


class Payment(Model):
    table = "payments"
    pk = "checkNumber"


class OrderDetail(Model):
    table = "orderdetails"
    pk = "orderNumber"


def ensure_database() -> None:
    if not SQL_FILE.exists():
        raise FileNotFoundError(f"Missing {SQL_FILE.name}")

    needs_rebuild = not DB_FILE.exists() or SQL_FILE.stat().st_mtime > DB_FILE.stat().st_mtime
    if not needs_rebuild:
        return

    if DB_FILE.exists():
        DB_FILE.unlink()

    sql_dump = SQL_FILE.read_text(encoding="utf-8", errors="replace")
    with db.connect() as conn:
        conn.executescript(DDL)
        for table, columns in SCHEMAS.items():
            rows = parse_insert_rows(sql_dump, table)
            if not rows:
                continue
            placeholders = ", ".join("?" for _ in columns)
            column_list = ", ".join(columns)
            conn.executemany(
                f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
                [tuple(row) for row in rows],
            )
        conn.commit()


def parse_insert_rows(sql: str, table: str) -> list[list[Any]]:
    pattern = re.compile(rf"insert\s+\s*into\s+{re.escape(table)}\([^)]*\)\s+values\s+", re.IGNORECASE)
    match = pattern.search(sql)
    if not match:
        return []

    next_insert = re.compile(r"\r?\n\s*insert\s+\s*into\s+", re.IGNORECASE)
    next_match = next_insert.search(sql, match.end())
    values_sql = sql[match.end() : next_match.start() if next_match else len(sql)]
    return parse_tuples(re.sub(r";\s*$", "", values_sql.strip()))


def parse_tuples(values_sql: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    row: list[Any] | None = None
    value: list[str] = []
    in_string = False
    escape = False
    depth = 0

    for char in values_sql:
        if in_string:
            if escape:
                value.append({"n": "\n", "r": "\r", "t": "\t"}.get(char, char))
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_string = False
            else:
                value.append(char)
            continue

        if char == "'":
            in_string = True
        elif char == "(":
            depth += 1
            if depth == 1:
                row = []
                value = []
            else:
                value.append(char)
        elif char == ")" and depth == 1:
            assert row is not None
            row.append(cast_sql_value("".join(value)))
            rows.append(row)
            row = None
            value = []
            depth = 0
        elif char == "," and depth == 1:
            assert row is not None
            row.append(cast_sql_value("".join(value)))
            value = []
        elif depth > 0:
            value.append(char)

    return rows


def cast_sql_value(raw: str) -> Any:
    value = raw.strip()
    if value.upper() == "NULL":
        return None
    if value == "":
        return ""
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def order_filters(params: dict[str, list[str]]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    values: list[Any] = []

    start = first_param(params, "start_date")
    end = first_param(params, "end_date")
    customer = first_param(params, "customer")
    country = first_param(params, "country")
    status = first_param(params, "status")
    product_line = first_param(params, "product_line")
    q = first_param(params, "q")

    if start:
        clauses.append("o.orderDate >= ?")
        values.append(start)
    if end:
        clauses.append("o.orderDate <= ?")
        values.append(end)
    if customer:
        clauses.append("c.customerNumber = ?")
        values.append(customer)
    if country:
        clauses.append("c.country = ?")
        values.append(country)
    if status:
        clauses.append("o.status = ?")
        values.append(status)
    if product_line:
        clauses.append("p.productLine = ?")
        values.append(product_line)
    if q:
        like = f"%{q}%"
        clauses.append(
            "(c.customerName LIKE ? OR c.country LIKE ? OR c.city LIKE ? OR o.status LIKE ? "
            "OR CAST(o.orderNumber AS TEXT) LIKE ? OR p.productName LIKE ? OR p.productLine LIKE ?)"
        )
        values.extend([like, like, like, like, like, like, like])

    return (" WHERE " + " AND ".join(clauses), values) if clauses else ("", values)


def revenue_expression() -> str:
    return "SUM(od.quantityOrdered * od.priceEach)"


def base_join() -> str:
    return """
        FROM orders o
        JOIN customers c ON c.customerNumber = o.customerNumber
        JOIN orderdetails od ON od.orderNumber = o.orderNumber
        JOIN products p ON p.productCode = od.productCode
    """


def api_meta(params: dict[str, list[str]] | None = None) -> dict[str, Any]:
    return {
        "customers": Customer.objects().order_by("customerName").all(),
        "countries": [row["country"] for row in db.query("SELECT DISTINCT country FROM customers ORDER BY country")],
        "statuses": [row["status"] for row in db.query("SELECT DISTINCT status FROM orders ORDER BY status")],
        "productLines": [row["productLine"] for row in db.query("SELECT DISTINCT productLine FROM products ORDER BY productLine")],
        "years": [row["year"] for row in db.query("SELECT DISTINCT substr(orderDate, 1, 4) AS year FROM orders ORDER BY year")],
        "dateRange": db.query("SELECT MIN(orderDate) AS startDate, MAX(orderDate) AS endDate FROM orders")[0],
    }


def api_stats(params: dict[str, list[str]]) -> dict[str, Any]:
    where, values = order_filters(params)
    total = db.query(
        f"""
        SELECT
          COUNT(DISTINCT o.orderNumber) AS orders,
          COUNT(DISTINCT c.customerNumber) AS customers,
          COUNT(DISTINCT p.productCode) AS products,
          COALESCE({revenue_expression()}, 0) AS revenue,
          COALESCE(SUM(od.quantityOrdered), 0) AS quantity
        {base_join()}
        {where}
        """,
        values,
    )[0]
    payments = db.scalar("SELECT COALESCE(SUM(amount), 0) FROM payments")
    total["payments"] = payments
    total["averageOrder"] = total["revenue"] / total["orders"] if total["orders"] else 0
    return total


def api_revenue_trend(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    where, values = order_filters(params)
    group = first_param(params, "group", "month")
    period_expr = "substr(o.orderDate, 1, 4)" if group == "year" else "substr(o.orderDate, 1, 7)"
    return db.query(
        f"""
        SELECT {period_expr} AS period,
               COALESCE({revenue_expression()}, 0) AS revenue,
               COUNT(DISTINCT o.orderNumber) AS orders
        {base_join()}
        {where}
        GROUP BY period
        ORDER BY period
        """,
        values,
    )


def api_status_report(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    where, values = order_filters(params)
    return db.query(
        f"""
        SELECT o.status,
               COALESCE({revenue_expression()}, 0) AS revenue,
               COUNT(DISTINCT o.orderNumber) AS orders
        {base_join()}
        {where}
        GROUP BY o.status
        ORDER BY revenue DESC
        """,
        values,
    )


def api_product_report(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    where, values = order_filters(params)
    return db.query(
        f"""
        SELECT p.productLine,
               COALESCE({revenue_expression()}, 0) AS revenue,
               COALESCE(SUM(od.quantityOrdered), 0) AS quantity,
               COUNT(DISTINCT p.productCode) AS products
        {base_join()}
        {where}
        GROUP BY p.productLine
        ORDER BY revenue DESC
        """,
        values,
    )


def api_top_customers(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    where, values = order_filters(params)
    limit = safe_int(first_param(params, "limit", "10"), 10)
    return db.query(
        f"""
        SELECT c.customerNumber,
               c.customerName,
               c.country,
               c.city,
               COUNT(DISTINCT o.orderNumber) AS orders,
               COALESCE({revenue_expression()}, 0) AS revenue
        {base_join()}
        {where}
        GROUP BY c.customerNumber, c.customerName, c.country, c.city
        ORDER BY revenue DESC
        LIMIT ?
        """,
        values + [limit],
    )


def api_orders(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    where, values = order_filters(params)
    limit = safe_int(first_param(params, "limit", "100"), 100)
    return db.query(
        f"""
        SELECT o.orderNumber,
               o.orderDate,
               o.requiredDate,
               o.shippedDate,
               o.status,
               c.customerNumber,
               c.customerName,
               c.city,
               c.country,
               GROUP_CONCAT(DISTINCT p.productLine) AS productLines,
               COALESCE(SUM(od.quantityOrdered), 0) AS quantity,
               COALESCE({revenue_expression()}, 0) AS revenue
        {base_join()}
        {where}
        GROUP BY o.orderNumber, o.orderDate, o.requiredDate, o.shippedDate, o.status,
                 c.customerNumber, c.customerName, c.city, c.country
        ORDER BY o.orderDate DESC, o.orderNumber DESC
        LIMIT ?
        """,
        values + [limit],
    )


def api_customers(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    q = first_param(params, "q")
    country = first_param(params, "country")
    query = Customer.objects()
    if q:
        like = f"%{q}%"
        query = query.where("(customerName LIKE ? OR contactFirstName LIKE ? OR contactLastName LIKE ? OR city LIKE ?)", like, like, like, like)
    if country:
        query = query.where("country = ?", country)
    return query.order_by("customerName").limit(safe_int(first_param(params, "limit", "100"), 100)).all()


def api_pivot(params: dict[str, list[str]]) -> dict[str, Any]:
    allowed_dimensions = {
        "customer": "c.customerName",
        "country": "c.country",
        "year": "substr(o.orderDate, 1, 4)",
        "month": "substr(o.orderDate, 1, 7)",
        "productLine": "p.productLine",
        "product": "p.productName",
        "status": "o.status",
    }
    allowed_metrics = {
        "revenue": f"COALESCE({revenue_expression()}, 0)",
        "orders": "COUNT(DISTINCT o.orderNumber)",
        "quantity": "COALESCE(SUM(od.quantityOrdered), 0)",
        "customers": "COUNT(DISTINCT c.customerNumber)",
    }
    row_key = first_param(params, "row", "country")
    col_key = first_param(params, "col", "year")
    metric_key = first_param(params, "metric", "revenue")
    if row_key not in allowed_dimensions or col_key not in allowed_dimensions or metric_key not in allowed_metrics:
        raise ValueError("Invalid pivot row, column, or metric")

    where, values = order_filters(params)
    row_expr = allowed_dimensions[row_key]
    col_expr = allowed_dimensions[col_key]
    metric_expr = allowed_metrics[metric_key]
    rows = db.query(
        f"""
        SELECT {row_expr} AS rowKey,
               {col_expr} AS colKey,
               {metric_expr} AS value
        {base_join()}
        {where}
        GROUP BY rowKey, colKey
        ORDER BY rowKey, colKey
        """,
        values,
    )
    return {
        "row": row_key,
        "col": col_key,
        "metric": metric_key,
        "rows": rows,
    }


def api_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    history = payload.get("history", [])
    if not message:
        raise ValueError("Message is required")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY. Start the server with: GEMINI_API_KEY='your_key' python3 server.py")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = build_chat_prompt(message, history if isinstance(history, list) else [])
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "topP": 0.9,
            "maxOutputTokens": 900,
        },
    }
    answer = call_gemini(api_key, model, body)
    return {"reply": answer, "model": model}


def build_chat_prompt(message: str, history: list[Any]) -> str:
    stats = api_stats({})
    top_customers = api_top_customers({"limit": ["5"]})
    products = api_product_report({})
    status = api_status_report({})
    trend = api_revenue_trend({"group": ["year"]})
    context = {
        "dateRange": api_meta({})["dateRange"],
        "stats": stats,
        "topCustomers": top_customers,
        "productLineRevenue": products,
        "orderStatusRevenue": status,
        "yearlyRevenue": trend,
    }
    safe_history = []
    for item in history[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", ""))[:20]
        content = str(item.get("content", ""))[:800]
        if role and content:
            safe_history.append({"role": role, "content": content})

    return f"""
You are a data assistant embedded in a ClassicModels analytics dashboard.
Answer in the same language as the user. Be concise and business-focused.
Use the JSON context below for ClassicModels questions. Do not invent rows or totals.
If the answer is not available in the provided context, say that the dashboard API needs a more specific report.

ClassicModels context JSON:
{json.dumps(context, ensure_ascii=False)}

Recent chat history:
{json.dumps(safe_history, ensure_ascii=False)}

User question:
{message}
""".strip()


def call_gemini(api_key: str, model: str, body: dict[str, Any]) -> str:
    url = f"{GEMINI_API_URL.format(model=model)}?key={api_key}"
    request = urlrequest.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error {exc.code}: {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Cannot reach Gemini API: {exc.reason}") from exc

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini API returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text", "")) for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini API returned an empty answer")
    return text


def first_param(params: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    value = params.get(key, [default])[0]
    return value if value not in ("", "all", None) else default


def safe_int(value: str | None, default: int) -> int:
    try:
        return max(1, min(int(value or default), 500))
    except ValueError:
        return default


class ApiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if parsed.path == "/":
                self.path = "/index.html"
            return super().do_GET()

        params = parse_qs(parsed.query)
        routes = {
            "/api/meta": api_meta,
            "/api/stats": api_stats,
            "/api/revenue/trend": api_revenue_trend,
            "/api/reports/status": api_status_report,
            "/api/reports/products": api_product_report,
            "/api/reports/top-customers": api_top_customers,
            "/api/orders": api_orders,
            "/api/customers": api_customers,
            "/api/pivot": api_pivot,
        }

        try:
            handler = routes.get(parsed.path)
            if handler is None:
                self.send_json({"error": "API endpoint not found"}, status=404)
                return
            self.send_json(handler(params))
        except Exception as exc:  # Keep API errors JSON-readable for the frontend.
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/chat":
            self.send_json({"error": "API endpoint not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            self.send_json(api_chat(payload))
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    load_local_env()
    ensure_database()
    port = int(os.environ.get("PORT", "8000"))
    server = ReusableThreadingHTTPServer(("0.0.0.0", port), ApiHandler)
    print(f"ClassicModels API running at http://localhost:{port}")
    print(f"SQLite database: {DB_FILE.name}")
    server.serve_forever()


if __name__ == "__main__":
    main()
