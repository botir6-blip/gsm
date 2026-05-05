from __future__ import annotations

import os
import tempfile
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DB_PATH = BASE_DIR / "sim_bonus.db"


def normalize_database_url(raw_url: str | None) -> str:
    """Railway Postgres gives DATABASE_URL. Locally we use SQLite."""
    if not raw_url:
        return f"sqlite:///{LOCAL_DB_PATH}"
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgresql://") and "+" not in raw_url.split("://", 1)[0]:
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL"))
CONNECT_ARGS = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine: Engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=CONNECT_ARGS,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    init_db()

    @app.context_processor
    def inject_now() -> dict[str, Any]:
        return {"now": datetime.now(), "current_year": datetime.now().year}

    @app.route("/health")
    def health() -> str:
        return "ok"

    @app.route("/sw.js")
    def service_worker() -> Response:
        response = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/")
    @login_required
    def dashboard() -> str:
        today = date.today().isoformat()
        month = request.args.get("month") or date.today().strftime("%Y-%m")
        with engine.connect() as conn:
            total_today = scalar(
                conn,
                "SELECT COALESCE(SUM(quantity), 0) AS total FROM sales WHERE sale_date = :today",
                {"today": today},
            )
            total_month = scalar(
                conn,
                "SELECT COALESCE(SUM(quantity), 0) AS total FROM sales WHERE substr(sale_date, 1, 7) = :month",
                {"month": month},
            )
            bonus_month = scalar(
                conn,
                """
                SELECT COALESCE(SUM(s.quantity * t.bonus_per_item), 0) AS total
                FROM sales s
                JOIN tariffs t ON t.id = s.tariff_id
                WHERE substr(s.sale_date, 1, 7) = :month
                """,
                {"month": month},
            )
            top_employees = fetch_all(
                conn,
                """
                SELECT e.full_name, COALESCE(SUM(s.quantity), 0) AS qty,
                       COALESCE(SUM(s.quantity * t.bonus_per_item), 0) AS bonus
                FROM sales s
                JOIN employees e ON e.id = s.employee_id
                JOIN tariffs t ON t.id = s.tariff_id
                WHERE substr(s.sale_date, 1, 7) = :month
                GROUP BY e.id, e.full_name
                ORDER BY qty DESC, e.full_name
                LIMIT 10
                """,
                {"month": month},
            )
            top_tariffs = fetch_all(
                conn,
                """
                SELECT t.name, COALESCE(SUM(s.quantity), 0) AS qty
                FROM sales s
                JOIN tariffs t ON t.id = s.tariff_id
                WHERE substr(s.sale_date, 1, 7) = :month
                GROUP BY t.id, t.name
                ORDER BY qty DESC, t.name
                LIMIT 10
                """,
                {"month": month},
            )
        return render_template(
            "dashboard.html",
            active="dashboard",
            month=month,
            total_today=total_today,
            total_month=total_month,
            bonus_month=bonus_month,
            top_employees=top_employees,
            top_tariffs=top_tariffs,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str | Response:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            with engine.connect() as conn:
                user = fetch_one(conn, "SELECT * FROM users WHERE username = :username", {"username": username})
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                flash("Хуш келибсиз!", "success")
                return redirect(url_for("dashboard"))
            flash("Логин ёки пароль нотўғри.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout() -> Response:
        session.clear()
        flash("Тизимдан чиқдингиз.", "info")
        return redirect(url_for("login"))

    @app.route("/password", methods=["GET", "POST"])
    @login_required
    def change_password() -> str | Response:
        if request.method == "POST":
            old_password = request.form.get("old_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if len(new_password) < 6:
                flash("Янги пароль камида 6 та белгидан иборат бўлиши керак.", "danger")
                return redirect(url_for("change_password"))
            if new_password != confirm_password:
                flash("Янги пароль такрори мос эмас.", "danger")
                return redirect(url_for("change_password"))
            with engine.begin() as conn:
                user = fetch_one(conn, "SELECT * FROM users WHERE id = :id", {"id": session["user_id"]})
                if not user or not check_password_hash(user["password_hash"], old_password):
                    flash("Эски пароль нотўғри.", "danger")
                    return redirect(url_for("change_password"))
                conn.execute(
                    text("UPDATE users SET password_hash = :hash WHERE id = :id"),
                    {"hash": generate_password_hash(new_password), "id": session["user_id"]},
                )
                add_audit(conn, "Пароль ўзгартирилди", session.get("username", "admin"))
            flash("Пароль ўзгартирилди.", "success")
            return redirect(url_for("dashboard"))
        return render_template("password.html", active="password")

    @app.route("/employees")
    @login_required
    def employees() -> str:
        with engine.connect() as conn:
            rows = fetch_all(conn, "SELECT * FROM employees ORDER BY is_active DESC, full_name")
        return render_template("employees.html", active="employees", rows=rows)

    @app.route("/employees/add", methods=["POST"])
    @login_required
    def add_employee() -> Response:
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Ходим Ф.И.О. киритилмаган.", "danger")
            return redirect(url_for("employees"))
        with engine.begin() as conn:
            try:
                conn.execute(
                    text("INSERT INTO employees(full_name, is_active) VALUES(:full_name, 1)"),
                    {"full_name": full_name},
                )
                add_audit(conn, "Ходим қўшилди", full_name)
                flash("Ходим қўшилди.", "success")
            except IntegrityError:
                flash("Бу Ф.И.О. аллақачон бор.", "warning")
        return redirect(url_for("employees"))

    @app.route("/employees/<int:employee_id>/edit", methods=["POST"])
    @login_required
    def edit_employee(employee_id: int) -> Response:
        full_name = request.form.get("full_name", "").strip()
        is_active = 1 if request.form.get("is_active") == "on" else 0
        if not full_name:
            flash("Ходим Ф.И.О. бўш бўлмаслиги керак.", "danger")
            return redirect(url_for("employees"))
        with engine.begin() as conn:
            try:
                conn.execute(
                    text("UPDATE employees SET full_name = :full_name, is_active = :is_active WHERE id = :id"),
                    {"full_name": full_name, "is_active": is_active, "id": employee_id},
                )
                add_audit(conn, "Ходим маълумоти ўзгартирилди", f"employee_id={employee_id}; {full_name}")
                flash("Ходим маълумоти сақланди.", "success")
            except IntegrityError:
                flash("Бу Ф.И.О. бошқа ходимда бор.", "warning")
        return redirect(url_for("employees"))

    @app.route("/tariffs")
    @login_required
    def tariffs() -> str:
        with engine.connect() as conn:
            rows = fetch_all(conn, "SELECT * FROM tariffs ORDER BY is_active DESC, name")
        return render_template("tariffs.html", active="tariffs", rows=rows)

    @app.route("/tariffs/add", methods=["POST"])
    @login_required
    def add_tariff() -> Response:
        name = request.form.get("name", "").strip()
        bonus = parse_int(request.form.get("bonus_per_item"))
        if not name:
            flash("Тариф номи киритилмаган.", "danger")
            return redirect(url_for("tariffs"))
        if bonus < 0:
            flash("Бонус суммаси манфий бўлмаслиги керак.", "danger")
            return redirect(url_for("tariffs"))
        with engine.begin() as conn:
            try:
                conn.execute(
                    text("INSERT INTO tariffs(name, bonus_per_item, is_active) VALUES(:name, :bonus, 1)"),
                    {"name": name, "bonus": bonus},
                )
                add_audit(conn, "Тариф қўшилди", f"{name}; бонус={bonus}")
                flash("Тариф қўшилди.", "success")
            except IntegrityError:
                flash("Бу тариф аллақачон бор.", "warning")
        return redirect(url_for("tariffs"))

    @app.route("/tariffs/<int:tariff_id>/edit", methods=["POST"])
    @login_required
    def edit_tariff(tariff_id: int) -> Response:
        name = request.form.get("name", "").strip()
        bonus = parse_int(request.form.get("bonus_per_item"))
        is_active = 1 if request.form.get("is_active") == "on" else 0
        if not name:
            flash("Тариф номи бўш бўлмаслиги керак.", "danger")
            return redirect(url_for("tariffs"))
        if bonus < 0:
            flash("Бонус суммаси манфий бўлмаслиги керак.", "danger")
            return redirect(url_for("tariffs"))
        with engine.begin() as conn:
            try:
                conn.execute(
                    text(
                        """
                        UPDATE tariffs
                        SET name = :name, bonus_per_item = :bonus, is_active = :is_active
                        WHERE id = :id
                        """
                    ),
                    {"name": name, "bonus": bonus, "is_active": is_active, "id": tariff_id},
                )
                add_audit(conn, "Тариф ўзгартирилди", f"tariff_id={tariff_id}; {name}; бонус={bonus}")
                flash("Тариф сақланди.", "success")
            except IntegrityError:
                flash("Бу тариф номи бошқа тарифда бор.", "warning")
        return redirect(url_for("tariffs"))

    @app.route("/sales/new", methods=["GET", "POST"])
    @login_required
    def sale_new() -> str | Response:
        if request.method == "POST":
            sale_date = request.form.get("sale_date", "").strip()
            employee_id = parse_int(request.form.get("employee_id"))
            tariff_id = parse_int(request.form.get("tariff_id"))
            quantity = parse_int(request.form.get("quantity"))
            comment = request.form.get("comment", "").strip()

            error = validate_sale_form(sale_date, employee_id, tariff_id, quantity)
            if error:
                flash(error, "danger")
                return redirect(url_for("sale_new"))
            month = sale_date[:7]
            if is_month_closed(month):
                flash("Бу ой ёпилган. Маълумот киритиш ёки ўзгартириш мумкин эмас.", "danger")
                return redirect(url_for("sale_new"))

            with engine.begin() as conn:
                duplicate = fetch_one(
                    conn,
                    """
                    SELECT id FROM sales
                    WHERE sale_date = :sale_date AND employee_id = :employee_id AND tariff_id = :tariff_id
                    """,
                    {"sale_date": sale_date, "employee_id": employee_id, "tariff_id": tariff_id},
                )
                if duplicate:
                    flash("Бу санада ушбу ходим учун бу тариф аллақачон киритилган.", "warning")
                    return redirect(url_for("sale_new"))
                conn.execute(
                    text(
                        """
                        INSERT INTO sales(sale_date, employee_id, tariff_id, quantity, comment, created_by)
                        VALUES(:sale_date, :employee_id, :tariff_id, :quantity, :comment, :created_by)
                        """
                    ),
                    {
                        "sale_date": sale_date,
                        "employee_id": employee_id,
                        "tariff_id": tariff_id,
                        "quantity": quantity,
                        "comment": comment,
                        "created_by": session.get("username", "admin"),
                    },
                )
                add_audit(conn, "Сотув қўшилди", f"{sale_date}, employee_id={employee_id}, tariff_id={tariff_id}, quantity={quantity}")
            flash("Сотув сақланди.", "success")
            return redirect(url_for("sale_new"))

        employees_list, tariffs_list = get_active_refs()
        return render_template(
            "sale_form.html",
            active="sale_new",
            sale=None,
            employees=employees_list,
            tariffs=tariffs_list,
            today=date.today().isoformat(),
        )

    @app.route("/sales/<int:sale_id>/edit", methods=["GET", "POST"])
    @login_required
    def sale_edit(sale_id: int) -> str | Response:
        with engine.connect() as conn:
            sale = fetch_one(conn, "SELECT * FROM sales WHERE id = :id", {"id": sale_id})
        if not sale:
            flash("Сотув топилмади.", "danger")
            return redirect(url_for("sales_journal"))

        if request.method == "POST":
            sale_date = request.form.get("sale_date", "").strip()
            employee_id = parse_int(request.form.get("employee_id"))
            tariff_id = parse_int(request.form.get("tariff_id"))
            quantity = parse_int(request.form.get("quantity"))
            comment = request.form.get("comment", "").strip()
            reason = request.form.get("reason", "").strip()

            error = validate_sale_form(sale_date, employee_id, tariff_id, quantity)
            if error:
                flash(error, "danger")
                return redirect(url_for("sale_edit", sale_id=sale_id))
            if not reason:
                flash("Ўзгартириш сабаби киритилиши шарт.", "danger")
                return redirect(url_for("sale_edit", sale_id=sale_id))
            if is_month_closed(sale_date[:7]) or is_month_closed(sale["sale_date"][:7]):
                flash("Бу ой ёпилган. Маълумотни ўзгартириш мумкин эмас.", "danger")
                return redirect(url_for("sales_journal"))

            with engine.begin() as conn:
                duplicate = fetch_one(
                    conn,
                    """
                    SELECT id FROM sales
                    WHERE sale_date = :sale_date AND employee_id = :employee_id
                      AND tariff_id = :tariff_id AND id <> :id
                    """,
                    {"sale_date": sale_date, "employee_id": employee_id, "tariff_id": tariff_id, "id": sale_id},
                )
                if duplicate:
                    flash("Бу санада ушбу ходим учун бу тариф аллақачон киритилган.", "warning")
                    return redirect(url_for("sale_edit", sale_id=sale_id))
                conn.execute(
                    text(
                        """
                        UPDATE sales
                        SET sale_date = :sale_date,
                            employee_id = :employee_id,
                            tariff_id = :tariff_id,
                            quantity = :quantity,
                            comment = :comment,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "sale_date": sale_date,
                        "employee_id": employee_id,
                        "tariff_id": tariff_id,
                        "quantity": quantity,
                        "comment": comment,
                        "id": sale_id,
                    },
                )
                add_audit(conn, "Сотув ўзгартирилди", f"sale_id={sale_id}; сабаб: {reason}")
            flash("Сотув ўзгартирилди.", "success")
            return redirect(url_for("sales_journal"))

        employees_list, tariffs_list = get_active_refs(include_ids=(sale["employee_id"], sale["tariff_id"]))
        return render_template(
            "sale_form.html",
            active="sales_journal",
            sale=sale,
            employees=employees_list,
            tariffs=tariffs_list,
            today=date.today().isoformat(),
        )

    @app.route("/sales/<int:sale_id>/delete", methods=["POST"])
    @login_required
    def sale_delete(sale_id: int) -> Response:
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("Ўчириш сабаби киритилиши шарт.", "danger")
            return redirect(url_for("sales_journal"))
        with engine.begin() as conn:
            sale = fetch_one(conn, "SELECT * FROM sales WHERE id = :id", {"id": sale_id})
            if not sale:
                flash("Сотув топилмади.", "danger")
                return redirect(url_for("sales_journal"))
            if is_month_closed(sale["sale_date"][:7]):
                flash("Бу ой ёпилган. Маълумотни ўчириш мумкин эмас.", "danger")
                return redirect(url_for("sales_journal"))
            conn.execute(text("DELETE FROM sales WHERE id = :id"), {"id": sale_id})
            add_audit(conn, "Сотув ўчирилди", f"sale_id={sale_id}; сабаб: {reason}")
        flash("Сотув ўчирилди.", "success")
        return redirect(url_for("sales_journal"))

    @app.route("/sales")
    @login_required
    def sales_journal() -> str:
        filters = get_filters()
        rows = fetch_sales(filters)
        employees_list, tariffs_list = get_all_refs()
        return render_template(
            "sales_journal.html",
            active="sales_journal",
            rows=rows,
            filters=filters,
            employees=employees_list,
            tariffs=tariffs_list,
        )

    @app.route("/report")
    @login_required
    def report() -> str:
        month = request.args.get("month") or date.today().strftime("%Y-%m")
        data = build_report(month)
        closed = is_month_closed(month)
        return render_template("report.html", active="report", month=month, closed=closed, **data)

    @app.route("/report/export")
    @login_required
    def report_export() -> Response:
        month = request.args.get("month") or date.today().strftime("%Y-%m")
        data = build_report(month)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        file_path = Path(tmp.name)
        create_excel_report(file_path, month, data)
        return send_file(file_path, as_attachment=True, download_name=f"bonus_hisobot_{month}.xlsx")

    @app.route("/month/close", methods=["POST"])
    @login_required
    def month_close() -> Response:
        month = request.form.get("month", "").strip()
        if not is_valid_month(month):
            flash("Ой формати нотўғри.", "danger")
            return redirect(url_for("report"))
        with engine.begin() as conn:
            existing = fetch_one(conn, "SELECT month FROM month_locks WHERE month = :month", {"month": month})
            if not existing:
                conn.execute(
                    text("INSERT INTO month_locks(month, closed_by, closed_at) VALUES(:month, :closed_by, CURRENT_TIMESTAMP)"),
                    {"month": month, "closed_by": session.get("username", "admin")},
                )
                add_audit(conn, "Ой ёпилди", month)
        flash(f"{month} ойи ёпилди.", "success")
        return redirect(url_for("report", month=month))

    @app.route("/month/open", methods=["POST"])
    @login_required
    def month_open() -> Response:
        month = request.form.get("month", "").strip()
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("Ойни қайта очиш сабаби киритилиши шарт.", "danger")
            return redirect(url_for("report", month=month))
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM month_locks WHERE month = :month"), {"month": month})
            add_audit(conn, "Ой қайта очилди", f"{month}; сабаб: {reason}")
        flash(f"{month} ойи қайта очилди.", "success")
        return redirect(url_for("report", month=month))

    @app.route("/audit")
    @login_required
    def audit() -> str:
        with engine.connect() as conn:
            rows = fetch_all(conn, "SELECT * FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT 200")
        return render_template("audit.html", active="audit", rows=rows)

    return app


def fetch_one(conn, sql: str, params: dict[str, Any] | None = None):
    return conn.execute(text(sql), params or {}).mappings().first()


def fetch_all(conn, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    return list(conn.execute(text(sql), params or {}).mappings().all())


def scalar(conn, sql: str, params: dict[str, Any] | None = None) -> Any:
    return conn.execute(text(sql), params or {}).scalar() or 0


def init_db() -> None:
    dialect = engine.dialect.name
    if dialect == "postgresql":
        id_column = "INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY"
    else:
        id_column = "INTEGER PRIMARY KEY AUTOINCREMENT"

    schema = f"""
    CREATE TABLE IF NOT EXISTS users (
        id {id_column},
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS employees (
        id {id_column},
        full_name TEXT NOT NULL UNIQUE,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tariffs (
        id {id_column},
        name TEXT NOT NULL UNIQUE,
        bonus_per_item INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sales (
        id {id_column},
        sale_date TEXT NOT NULL,
        employee_id INTEGER NOT NULL,
        tariff_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        comment TEXT,
        created_by TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(tariff_id) REFERENCES tariffs(id),
        UNIQUE(sale_date, employee_id, tariff_id)
    );

    CREATE TABLE IF NOT EXISTS month_locks (
        month TEXT PRIMARY KEY,
        closed_by TEXT,
        closed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id {id_column},
        action TEXT NOT NULL,
        details TEXT,
        username TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """
    with engine.begin() as conn:
        for statement in schema.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))

        # Агар база аввал бошқа версия/бошқа проект учун ишлатилган бўлса,
        # CREATE TABLE IF NOT EXISTS мавжуд жадвалларга янги устун қўшмайди.
        # Шунинг учун керакли устунларни хавфсиз тарзда қўшиб чиқамиз.
        ensure_schema_compatibility(conn)

        # Эски база қайта ишлатилганда users жадвалида бошқа фойдаланувчилар бўлиши мумкин.
        # Шунинг учун admin бор-йўқлигини умумий user_count билан эмас, username орқали текширамиз.
        admin_user = fetch_one(conn, "SELECT id, password_hash FROM users WHERE username = :username", {"username": "admin"})
        if not admin_user:
            conn.execute(
                text("INSERT INTO users(username, password_hash) VALUES(:username, :password_hash)"),
                {"username": "admin", "password_hash": generate_password_hash("admin123")},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO audit_logs(action, details, username, created_at)
                    VALUES(:action, :details, :username, CURRENT_TIMESTAMP)
                    """
                ),
                {"action": "Тизим яратилди", "details": "Биринчи admin фойдаланувчи қўшилди", "username": "system"},
            )
        elif not admin_user["password_hash"]:
            conn.execute(
                text("UPDATE users SET password_hash = :password_hash WHERE username = :username"),
                {"username": "admin", "password_hash": generate_password_hash("admin123")},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO audit_logs(action, details, username, created_at)
                    VALUES(:action, :details, :username, CURRENT_TIMESTAMP)
                    """
                ),
                {"action": "Admin пароль тикланди", "details": "admin123 вақтинча пароль ўрнатилди", "username": "system"},
            )


def ensure_schema_compatibility(conn) -> None:
    """Add missing columns when an existing Railway/Postgres DB is reused."""
    columns_by_table = {
        "users": {
            "username": "TEXT",
            "password_hash": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        "employees": {
            "full_name": "TEXT",
            "is_active": "INTEGER DEFAULT 1",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        "tariffs": {
            "name": "TEXT",
            "bonus_per_item": "INTEGER DEFAULT 0",
            "is_active": "INTEGER DEFAULT 1",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        "sales": {
            "sale_date": "TEXT",
            "employee_id": "INTEGER",
            "tariff_id": "INTEGER",
            "quantity": "INTEGER DEFAULT 0",
            "comment": "TEXT",
            "created_by": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
        "month_locks": {
            "closed_by": "TEXT",
            "closed_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
        "audit_logs": {
            "action": "TEXT",
            "details": "TEXT",
            "username": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        },
    }

    if engine.dialect.name == "postgresql":
        for table, columns in columns_by_table.items():
            for column, column_type in columns.items():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}"))
        return

    # SQLite учун: ALTER TABLE ... ADD COLUMN IF NOT EXISTS ҳамма муҳитда ишламаслиги мумкин.
    # Бундан ташқари SQLite мавжуд жадвалга CURRENT_TIMESTAMP default билан устун қўшишга рухсат бермаслиги мумкин.
    for table, columns in columns_by_table.items():
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
        for column, column_type in columns.items():
            if column not in existing:
                safe_column_type = column_type.replace(" DEFAULT CURRENT_TIMESTAMP", "")
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {safe_column_type}"))



def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


def parse_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(str(value).replace(" ", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0


def money(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except Exception:
        return "0"


def qty(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except Exception:
        return "0"


def is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def is_valid_month(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m")
        return True
    except ValueError:
        return False


def validate_sale_form(sale_date: str, employee_id: int, tariff_id: int, quantity: int) -> str | None:
    if not is_valid_date(sale_date):
        return "Сана нотўғри киритилган."
    if employee_id <= 0:
        return "Ходим танланмаган."
    if tariff_id <= 0:
        return "Тариф танланмаган."
    if quantity <= 0:
        return "Сотилган SIM-карта сони 0 дан катта бўлиши керак."
    return None


def get_active_refs(include_ids: tuple[int, int] | None = None) -> tuple[list[Any], list[Any]]:
    include_employee_id, include_tariff_id = include_ids or (0, 0)
    with engine.connect() as conn:
        employees = fetch_all(
            conn,
            "SELECT * FROM employees WHERE is_active = 1 OR id = :id ORDER BY full_name",
            {"id": include_employee_id},
        )
        tariffs = fetch_all(
            conn,
            "SELECT * FROM tariffs WHERE is_active = 1 OR id = :id ORDER BY name",
            {"id": include_tariff_id},
        )
    return employees, tariffs


def get_all_refs() -> tuple[list[Any], list[Any]]:
    with engine.connect() as conn:
        employees = fetch_all(conn, "SELECT * FROM employees ORDER BY full_name")
        tariffs = fetch_all(conn, "SELECT * FROM tariffs ORDER BY name")
    return employees, tariffs


def get_filters() -> dict[str, Any]:
    return {
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
        "employee_id": parse_int(request.args.get("employee_id")),
        "tariff_id": parse_int(request.args.get("tariff_id")),
        "q": request.args.get("q", "").strip(),
    }


def fetch_sales(filters: dict[str, Any]) -> list[Any]:
    sql = [
        """
        SELECT s.*, e.full_name, t.name AS tariff_name, t.bonus_per_item,
               (s.quantity * t.bonus_per_item) AS bonus_total
        FROM sales s
        JOIN employees e ON e.id = s.employee_id
        JOIN tariffs t ON t.id = s.tariff_id
        WHERE 1=1
        """
    ]
    params: dict[str, Any] = {}
    if filters["date_from"]:
        sql.append("AND s.sale_date >= :date_from")
        params["date_from"] = filters["date_from"]
    if filters["date_to"]:
        sql.append("AND s.sale_date <= :date_to")
        params["date_to"] = filters["date_to"]
    if filters["employee_id"]:
        sql.append("AND s.employee_id = :employee_id")
        params["employee_id"] = filters["employee_id"]
    if filters["tariff_id"]:
        sql.append("AND s.tariff_id = :tariff_id")
        params["tariff_id"] = filters["tariff_id"]
    if filters["q"]:
        sql.append("AND (e.full_name LIKE :q OR t.name LIKE :q OR s.comment LIKE :q)")
        params["q"] = f"%{filters['q']}%"
    sql.append("ORDER BY s.sale_date DESC, e.full_name, t.name")
    with engine.connect() as conn:
        return fetch_all(conn, " ".join(sql), params)


def build_report(month: str) -> dict[str, Any]:
    if not is_valid_month(month):
        month = date.today().strftime("%Y-%m")
    with engine.connect() as conn:
        detail = fetch_all(
            conn,
            """
            SELECT e.full_name, t.name AS tariff_name, t.bonus_per_item,
                   SUM(s.quantity) AS total_qty,
                   SUM(s.quantity * t.bonus_per_item) AS total_bonus
            FROM sales s
            JOIN employees e ON e.id = s.employee_id
            JOIN tariffs t ON t.id = s.tariff_id
            WHERE substr(s.sale_date, 1, 7) = :month
            GROUP BY e.id, e.full_name, t.id, t.name, t.bonus_per_item
            ORDER BY e.full_name, t.name
            """,
            {"month": month},
        )
        summary = fetch_all(
            conn,
            """
            SELECT e.full_name,
                   SUM(s.quantity) AS total_qty,
                   SUM(s.quantity * t.bonus_per_item) AS total_bonus
            FROM sales s
            JOIN employees e ON e.id = s.employee_id
            JOIN tariffs t ON t.id = s.tariff_id
            WHERE substr(s.sale_date, 1, 7) = :month
            GROUP BY e.id, e.full_name
            ORDER BY total_bonus DESC, e.full_name
            """,
            {"month": month},
        )
        totals = fetch_one(
            conn,
            """
            SELECT COALESCE(SUM(s.quantity), 0) AS total_qty,
                   COALESCE(SUM(s.quantity * t.bonus_per_item), 0) AS total_bonus
            FROM sales s
            JOIN tariffs t ON t.id = s.tariff_id
            WHERE substr(s.sale_date, 1, 7) = :month
            """,
            {"month": month},
        )
    return {"detail": detail, "summary": summary, "totals": totals or {"total_qty": 0, "total_bonus": 0}}


def is_month_closed(month: str) -> bool:
    if not is_valid_month(month):
        return False
    with engine.connect() as conn:
        row = fetch_one(conn, "SELECT month FROM month_locks WHERE month = :month", {"month": month})
    return row is not None


def add_audit(conn, action: str, details: str) -> None:
    username = session.get("username", "admin") if session else "admin"
    conn.execute(
        text(
            """
            INSERT INTO audit_logs(action, details, username, created_at)
            VALUES(:action, :details, :username, CURRENT_TIMESTAMP)
            """
        ),
        {"action": action, "details": details, "username": username},
    )


def create_excel_report(file_path: Path, month: str, data: dict[str, Any]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ойлик ҳисобот"
    ws.append([f"I-MAX — SIM-карта сотувлари бўйича бонус ҳисоботи — {month}"])
    ws.merge_cells("A1:E1")
    ws["A1"].font = Font(size=14, bold=True)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.append([])
    ws.append(["Ходим Ф.И.О.", "Тариф номи", "Сони", "1 дона бонус", "Жами бонус"])
    header_row = 3
    for cell in ws[header_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
        cell.alignment = Alignment(horizontal="center")

    for row in data["detail"]:
        ws.append([
            row["full_name"],
            row["tariff_name"],
            row["total_qty"],
            row["bonus_per_item"],
            row["total_bonus"],
        ])
    ws.append([])
    ws.append(["ЖАМИ", "", data["totals"]["total_qty"], "", data["totals"]["total_bonus"]])
    total_row = ws.max_row
    for cell in ws[total_row]:
        cell.font = Font(bold=True)

    ws2 = wb.create_sheet("Ходимлар бўйича жами")
    ws2.append([f"I-MAX — ходимлар бўйича умумий натижа — {month}"])
    ws2.merge_cells("A1:C1")
    ws2["A1"].font = Font(size=14, bold=True)
    ws2["A1"].alignment = Alignment(horizontal="center")
    ws2.append([])
    ws2.append(["Ходим Ф.И.О.", "Жами SIM", "Жами бонус"])
    for cell in ws2[3]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
        cell.alignment = Alignment(horizontal="center")
    for row in data["summary"]:
        ws2.append([row["full_name"], row["total_qty"], row["total_bonus"]])
    ws2.append([])
    ws2.append(["ЖАМИ", data["totals"]["total_qty"], data["totals"]["total_bonus"]])
    for cell in ws2[ws2.max_row]:
        cell.font = Font(bold=True)

    thin = Side(style="thin", color="CCCCCC")
    for sheet in (ws, ws2):
        for row in sheet.iter_rows():
            for cell in row:
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
        for col_idx in range(1, sheet.max_column + 1):
            max_len = 12
            col_letter = get_column_letter(col_idx)
            for cell in sheet[col_letter]:
                if cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)) + 2)
            sheet.column_dimensions[col_letter].width = min(max_len, 45)
        for row_idx in range(4, sheet.max_row + 1):
            for col_idx in range(2, sheet.max_column + 1):
                cell = sheet.cell(row_idx, col_idx)
                if isinstance(cell.value, int):
                    cell.number_format = '#,##0'

    wb.save(file_path)


app = create_app()
app.jinja_env.filters["money"] = money
app.jinja_env.filters["qty"] = qty

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", host="0.0.0.0", port=port)
