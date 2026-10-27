"""Shiridi Sai Cements - online cement and iron booking.

Flask + SQLite. Start it with:  python app.py
Customers book without signing in; the admin logs in, enters prices and
approves each bill before the customer can see it.
"""
import copy
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps

from flask import (Flask, abort, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from shop_config import BUSINESS, CATALOG

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(INSTANCE_DIR, "shiridi_sai.db"))

IST = timezone(timedelta(hours=5, minutes=30))
CENT = Decimal("0.01")
MAX_MONEY = Decimal("100000000")

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "admin@123"


def load_secret_key():
    """Use SECRET_KEY if set, otherwise create one once and keep it on disk."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    path = os.path.join(INSTANCE_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS_ONLY") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=64 * 1024,
)

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    must_change INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT UNIQUE,
    token TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    customer_note TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    other_charges TEXT NOT NULL DEFAULT '0',
    total TEXT,
    admin_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('cement', 'iron')),
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity TEXT NOT NULL,
    unit_price TEXT,
    amount TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
"""


def init_db():
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
        if con.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
            username = os.environ.get("ADMIN_USERNAME", DEFAULT_ADMIN_USER)
            password = os.environ.get("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
            con.execute(
                "INSERT INTO admins (username, password_hash, must_change) VALUES (?, ?, 1)",
                (username, generate_password_hash(password)),
            )
        # If ADMIN_PASSWORD is set (for example in the PythonAnywhere WSGI file) it always
        # wins: change it there, reload the site, and that is the new admin password.
        # Remove the ADMIN_PASSWORD line to manage the password from Admin > Settings instead.
        env_password = os.environ.get("ADMIN_PASSWORD")
        if env_password:
            username = os.environ.get("ADMIN_USERNAME", DEFAULT_ADMIN_USER)
            row = con.execute("SELECT id, password_hash FROM admins ORDER BY id LIMIT 1").fetchone()
            if row is not None:
                new_hash = row[1]
                if not check_password_hash(row[1], env_password):
                    new_hash = generate_password_hash(env_password)
                con.execute(
                    "UPDATE admins SET username = ?, password_hash = ?, must_change = 0 WHERE id = ?",
                    (username, new_hash, row[0]),
                )
        con.commit()
    finally:
        con.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def now_dt():
    return datetime.now(IST)


def now_str():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def format_inr(value):
    """12345.5 -> Rs 12,345.50 using Indian digit grouping."""
    if value is None or value == "":
        return ""
    amount = money(value)
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        whole = f"{head},{tail}"
    return f"{sign}₹{whole}.{frac}"


def format_qty(value):
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def format_dt(value):
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return value


app.jinja_env.filters["inr"] = format_inr
app.jinja_env.filters["qty"] = format_qty
app.jinja_env.filters["dt"] = format_dt


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def verify_csrf():
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    if not sent or not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Your session expired. Please refresh the page and try again.")


IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "svg")


def find_static_image(base):
    """URL of static/<base>.<ext> if a picture with that name exists, otherwise None."""
    for ext in IMAGE_EXTS:
        name = f"{base}.{ext}"
        if os.path.isfile(os.path.join(app.static_folder, name)):
            return url_for("static", filename=name)
    return None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def catalog_with_images():
    """Catalog plus pictures. Your own photo (jpg/png/webp) wins over the built-in drawing.

    Category picture:  static/images/cement.jpg  or  static/images/iron.jpg
    Product picture:   static/images/products/<product-name>.jpg   e.g. ultratech.jpg, tmt-bar-12-mm.jpg
    """
    view = copy.deepcopy(CATALOG)
    for key, spec in view.items():
        spec["image"] = find_static_image(f"images/{key}")
        spec["images"] = {}
        for name in spec["items"]:
            url = find_static_image(f"images/products/{slugify(name)}")
            if url:
                spec["images"][name] = url
    return view


@app.context_processor
def inject_globals():
    return {
        "business": BUSINESS,
        "catalog": catalog_with_images(),
        "csrf_token": csrf_token,
        "year": now_dt().year,
    }


_hits = {}
_fails = {}


def rate_limited(key, limit, window):
    """True when `key` already made `limit` calls within the last `window` seconds."""
    now = time.time()
    recent = [t for t in _hits.get(key, []) if now - t < window]
    if len(recent) >= limit:
        _hits[key] = recent
        return True
    recent.append(now)
    _hits[key] = recent
    return False


def login_locked(ip):
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 600]
    _fails[ip] = recent
    return len(recent) >= 5


def record_login_failure(ip):
    _fails.setdefault(ip, []).append(time.time())


def normalize_phone(raw):
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def clean_text(value, label, minimum, maximum, required=True):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text and not required:
        return ""
    if len(text) < minimum:
        raise ValueError(f"Please enter your {label}.")
    if len(text) > maximum:
        raise ValueError(f"{label.capitalize()} is too long (maximum {maximum} characters).")
    return text


def to_decimal(value, label):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Enter a valid number for {label}.")
    if not number.is_finite():
        raise ValueError(f"Enter a valid number for {label}.")
    return number


def parse_items(raw):
    """Validate the cart sent by the customer against the catalog."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("Add at least one item to your order.")
    if len(raw) > 30:
        raise ValueError("Too many items in one order (maximum 30).")
    items = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("Invalid item in your order.")
        category, name, unit = row.get("category"), row.get("name"), row.get("unit")
        spec = CATALOG.get(category)
        if not spec or name not in spec["items"] or unit not in spec["units"]:
            raise ValueError("One of the selected products is not available.")
        qty = to_decimal(row.get("quantity"), "quantity")
        if unit == "Tons":
            if qty <= 0 or qty > 1000 or qty != qty.quantize(Decimal("0.001")):
                raise ValueError("Tons must be between 0.001 and 1000 (up to 3 decimals).")
            qty_text = format(qty.normalize(), "f")
        else:
            if qty <= 0 or qty > 100000 or qty != qty.to_integral_value():
                raise ValueError(f"{unit} must be a whole number between 1 and 100000.")
            qty_text = str(int(qty))
        items.append((category, name, unit, qty_text))
    return items


def load_order_row(column, value):
    row = get_db().execute(f"SELECT * FROM orders WHERE {column} = ?", (value,)).fetchone()
    if row is None:
        return None
    order = dict(row)
    order["other_charges"] = Decimal(order["other_charges"] or "0")
    order["total"] = Decimal(order["total"]) if order["total"] is not None else None
    return order


def load_items(order_id):
    rows = get_db().execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["quantity"] = Decimal(item["quantity"])
        item["unit_price"] = Decimal(item["unit_price"]) if item["unit_price"] is not None else None
        item["amount"] = Decimal(item["amount"]) if item["amount"] is not None else None
        items.append(item)
    return items


def subtotal_of(items):
    return sum((i["amount"] for i in items if i["amount"] is not None), Decimal("0"))


# --------------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------------

@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    if request.path.startswith(("/api/", "/admin", "/order/")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(HTTPException)
def handle_http_error(err):
    if request.path.startswith("/api/"):
        return jsonify(error=err.description), err.code
    return render_template("error.html", code=err.code, message=err.description), err.code


# --------------------------------------------------------------------------
# Customer pages (no sign-in)
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html", track_error=bool(request.args.get("track_error")))


@app.post("/api/orders")
def api_create_order():
    if rate_limited(f"order:{request.remote_addr}", 15, 3600):
        return jsonify(error="Too many bookings from this device. Please try again later."), 429
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Invalid request."), 400
    try:
        name = clean_text(data.get("name"), "name", 2, 80)
        phone = normalize_phone(data.get("phone"))
        if phone is None:
            raise ValueError("Enter a valid 10-digit mobile number.")
        address = clean_text(data.get("address"), "delivery address", 5, 300)
        note = clean_text(data.get("note"), "note", 0, 200, required=False)
        items = parse_items(data.get("items"))
    except ValueError as err:
        return jsonify(error=str(err)), 400

    db = get_db()
    now = now_str()
    token = secrets.token_urlsafe(12)
    cur = db.execute(
        "INSERT INTO orders (token, customer_name, phone, address, customer_note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (token, name, phone, address, note, now, now),
    )
    order_id = cur.lastrowid
    order_no = f"SSC-{now_dt():%Y%m%d}-{order_id:04d}"
    db.execute("UPDATE orders SET order_no = ? WHERE id = ?", (order_no, order_id))
    db.executemany(
        "INSERT INTO order_items (order_id, category, name, unit, quantity) VALUES (?, ?, ?, ?, ?)",
        [(order_id, c, n, u, q) for c, n, u, q in items],
    )
    db.commit()
    return jsonify(order_no=order_no, token=token, url=url_for("order_page", token=token)), 201


@app.get("/order/<token>")
def order_page(token):
    order = load_order_row("token", token)
    if order is None:
        abort(404, "We could not find that order.")
    items = load_items(order["id"])
    show_prices = order["status"] == "approved"
    return render_template(
        "order.html", order=order, items=items, show_prices=show_prices,
        subtotal=subtotal_of(items) if show_prices else None,
    )


@app.get("/api/order/<token>/status")
def api_order_status(token):
    order = load_order_row("token", token)
    if order is None:
        return jsonify(error="Order not found."), 404
    return jsonify(status=order["status"])


@app.post("/track")
def track_order():
    if rate_limited(f"track:{request.remote_addr}", 20, 600):
        abort(429, "Too many attempts. Please wait a few minutes and try again.")
    order_no = request.form.get("order_no", "").strip().upper()
    phone = normalize_phone(request.form.get("phone"))
    if order_no and phone:
        row = get_db().execute(
            "SELECT token FROM orders WHERE order_no = ? AND phone = ?", (order_no, phone)
        ).fetchone()
        if row:
            return redirect(url_for("order_page", token=row["token"]))
    return redirect(url_for("index", track_error=1) + "#track")


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------

def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in again."), 401
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def safe_next(target):
    if target and target.startswith("/admin") and not target.startswith("//"):
        return target
    return url_for("admin_dashboard")


def current_admin():
    return get_db().execute(
        "SELECT * FROM admins WHERE id = ?", (session.get("admin_id"),)
    ).fetchone()


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    error = None
    if request.method == "POST":
        verify_csrf()
        ip = request.remote_addr
        if login_locked(ip):
            error = "Too many failed attempts. Please wait 10 minutes and try again."
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            admin = get_db().execute(
                "SELECT * FROM admins WHERE username = ?", (username,)
            ).fetchone()
            if admin and check_password_hash(admin["password_hash"], password):
                session.clear()
                session["admin_id"] = admin["id"]
                session["csrf"] = secrets.token_hex(16)
                session.permanent = True
                return redirect(safe_next(request.args.get("next")))
            record_login_failure(ip)
            error = "Incorrect username or password."
    return render_template("admin_login.html", error=error)


@app.post("/admin/logout")
def admin_logout():
    verify_csrf()
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    status = request.args.get("status", "pending")
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    query = request.args.get("q", "").strip()[:60]
    like = f"%{query}%"
    orders = [dict(r) for r in db.execute(
        "SELECT * FROM orders WHERE (? = 'all' OR status = ?) "
        "AND (? = '' OR order_no LIKE ? OR customer_name LIKE ? OR phone LIKE ?) "
        "ORDER BY id DESC LIMIT 200",
        (status, status, query, like, like, like),
    )]
    if orders:
        ids = [o["id"] for o in orders]
        marks = ",".join("?" * len(ids))
        grouped = {}
        for row in db.execute(
            f"SELECT * FROM order_items WHERE order_id IN ({marks}) ORDER BY id", ids
        ):
            grouped.setdefault(row["order_id"], []).append(
                f"{row['name']} × {format_qty(row['quantity'])} {row['unit'].lower()}"
            )
        for order in orders:
            parts = grouped.get(order["id"], [])
            order["summary"] = ", ".join(parts[:2]) + (f" +{len(parts) - 2} more" if len(parts) > 2 else "")
    counts = {"pending": 0, "approved": 0, "rejected": 0}
    for row in db.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status"):
        counts[row["status"]] = row["n"]
    latest = db.execute("SELECT COALESCE(MAX(id), 0) AS m FROM orders").fetchone()["m"]
    return render_template(
        "admin_dashboard.html", orders=orders, counts=counts, status=status,
        query=query, latest_id=latest, admin=current_admin(),
    )


@app.get("/api/admin/summary")
@admin_required
def api_admin_summary():
    db = get_db()
    pending = db.execute("SELECT COUNT(*) AS n FROM orders WHERE status = 'pending'").fetchone()["n"]
    latest = db.execute("SELECT COALESCE(MAX(id), 0) AS m FROM orders").fetchone()["m"]
    return jsonify(pending=pending, latest_id=latest)


@app.get("/admin/order/<int:order_id>")
@admin_required
def admin_order(order_id):
    order = load_order_row("id", order_id)
    if order is None:
        abort(404, "Order not found.")
    items = load_items(order_id)
    return render_template(
        "admin_order.html", order=order, items=items, admin=current_admin(),
        subtotal=subtotal_of(items), show_prices=order["status"] == "approved",
    )


@app.post("/api/admin/orders/<int:order_id>")
@admin_required
def api_admin_order_action(order_id):
    verify_csrf()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Invalid request."), 400
    order = load_order_row("id", order_id)
    if order is None:
        return jsonify(error="Order not found."), 404
    action = data.get("action")
    db = get_db()
    now = now_str()

    if action == "reopen":
        if order["status"] == "pending":
            return jsonify(error="This order is already open for pricing."), 409
        db.execute(
            "UPDATE orders SET status = 'pending', total = NULL, decided_at = NULL, updated_at = ? WHERE id = ?",
            (now, order_id),
        )
        db.commit()
        return jsonify(ok=True, message="Order reopened. The customer will see the waiting message again.")

    if order["status"] != "pending":
        return jsonify(error="This order is already closed. Use Reopen to change it."), 409

    try:
        note = clean_text(data.get("admin_note"), "note", 0, 300, required=False)
    except ValueError as err:
        return jsonify(error=str(err)), 400

    if action == "reject":
        db.execute(
            "UPDATE orders SET status = 'rejected', admin_note = ?, decided_at = ?, updated_at = ? WHERE id = ?",
            (note, now, now, order_id),
        )
        db.commit()
        return jsonify(ok=True, message="Order rejected. The customer has been notified on their bill page.")

    if action not in ("save", "approve"):
        return jsonify(error="Unknown action."), 400

    items = load_items(order_id)
    prices = data.get("prices")
    if not isinstance(prices, dict):
        return jsonify(error="Invalid prices."), 400
    try:
        rows = []
        for item in items:
            raw = str(prices.get(str(item["id"]), "")).strip()
            if raw == "":
                if action == "approve":
                    raise ValueError(f"Enter a price for {item['name']} before approving.")
                rows.append((None, None, item["id"]))
                continue
            price = to_decimal(raw, f"the price of {item['name']}")
            if price < 0 or price > MAX_MONEY:
                raise ValueError(f"The price of {item['name']} is out of range.")
            if action == "approve" and price == 0:
                raise ValueError(f"The price of {item['name']} cannot be 0.")
            price = money(price)
            rows.append((str(price), str(money(price * item["quantity"])), item["id"]))
        raw_other = str(data.get("other_charges", "")).strip() or "0"
        other = money(to_decimal(raw_other, "other charges"))
        if other < 0 or other > MAX_MONEY:
            raise ValueError("Other charges are out of range.")
    except ValueError as err:
        return jsonify(error=str(err)), 400

    db.executemany("UPDATE order_items SET unit_price = ?, amount = ? WHERE id = ?", rows)
    total = sum((Decimal(r[1]) for r in rows if r[1] is not None), Decimal("0")) + other
    if action == "approve":
        db.execute(
            "UPDATE orders SET status = 'approved', other_charges = ?, total = ?, admin_note = ?, "
            "decided_at = ?, updated_at = ? WHERE id = ?",
            (str(other), str(money(total)), note, now, now, order_id),
        )
        message = "Bill approved and sent. The customer can now see the final prices."
    else:
        db.execute(
            "UPDATE orders SET other_charges = ?, total = NULL, admin_note = ?, updated_at = ? WHERE id = ?",
            (str(other), note, now, order_id),
        )
        message = "Draft saved. The customer still sees the waiting message."
    db.commit()
    return jsonify(ok=True, message=message)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    admin = current_admin()
    error = done = None
    if request.method == "POST":
        verify_csrf()
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")
        if not check_password_hash(admin["password_hash"], current):
            error = "Your current password is not correct."
        elif len(new) < 8:
            error = "The new password must be at least 8 characters."
        elif new != confirm:
            error = "The new password and confirmation do not match."
        elif new == current:
            error = "Choose a password different from the current one."
        else:
            db = get_db()
            db.execute(
                "UPDATE admins SET password_hash = ?, must_change = 0 WHERE id = ?",
                (generate_password_hash(new), admin["id"]),
            )
            db.commit()
            done = "Password changed successfully."
            admin = current_admin()
    return render_template("admin_settings.html", admin=admin, error=error, done=done)


init_db()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
