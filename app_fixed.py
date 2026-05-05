from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import app as core

app = core.app


def now_db() -> datetime:
    return datetime.now().replace(microsecond=0)


def next_id(conn, table_name: str) -> int:
    allowed_tables = {"users", "employees", "tariffs", "sales", "audit_logs"}
    if table_name not in allowed_tables:
        raise ValueError(f"Unsupported table for next_id: {table_name}")
    return int(conn.execute(text(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table_name}")).scalar() or 1)


def db_error_text(error: Exception) -> str:
    return str(getattr(error, "orig", error)).replace("\n", " ")[:500]


def add_audit_safe(conn, action: str, details: str) -> None:
    username = session.get("username", "admin") if session else "admin"
    try:
        conn.execute(
            text(
                """
                INSERT INTO audit_logs(id, action, details, username, created_at)
                VALUES(:id, :action, :details, :username, :created_at)
                """
            ),
            {
                "id": next_id(conn, "audit_logs"),
                "action": action,
                "details": details,
                "username": username,
                "created_at": now_db(),
            },
        )
    except Exception as exc:
        print(f"AUDIT_LOG_ERROR: {db_error_text(exc)}")


core.add_audit = add_audit_safe


def add_employee_safe():
    full_name = request.form.get("full_name", "").strip()
    if not full_name:
        flash("Ходим Ф.И.О. киритилмаган.", "danger")
        return redirect(url_for("employees"))
    with core.engine.begin() as conn:
        try:
            existing = core.fetch_one(
                conn,
                "SELECT id FROM employees WHERE lower(trim(full_name)) = lower(trim(:full_name))",
                {"full_name": full_name},
            )
            if existing:
                flash("Бу Ф.И.О. аллақачон бор.", "warning")
                return redirect(url_for("employees"))
            conn.execute(
                text(
                    """
                    INSERT INTO employees(id, full_name, is_active, created_at)
                    VALUES(:id, :full_name, 1, :created_at)
                    """
                ),
                {"id": next_id(conn, "employees"), "full_name": full_name, "created_at": now_db()},
            )
            add_audit_safe(conn, "Ходим қўшилди", full_name)
            flash("Ходим қўшилди.", "success")
        except IntegrityError as exc:
            flash(f"Ходим қўшишда база хатоси: {db_error_text(exc)}", "danger")
        except Exception as exc:
            flash(f"Ходим қўшишда хато: {db_error_text(exc)}", "danger")
    return redirect(url_for("employees"))


def add_tariff_safe():
    name = core.tariff_name_display(request.form.get("name", ""))
    bonus = core.parse_int(request.form.get("bonus_per_item"))
    if not name:
        flash("Тариф номи киритилмаган.", "danger")
        return redirect(url_for("tariffs"))
    if bonus < 0:
        flash("Бонус суммаси манфий бўлмаслиги керак.", "danger")
        return redirect(url_for("tariffs"))
    with core.engine.begin() as conn:
        try:
            existing = core.fetch_one(
                conn,
                "SELECT id FROM tariffs WHERE lower(trim(name)) = lower(trim(:name))",
                {"name": name},
            )
            if existing:
                flash("Бу тариф аллақачон бор.", "warning")
                return redirect(url_for("tariffs"))
            conn.execute(
                text(
                    """
                    INSERT INTO tariffs(id, name, bonus_per_item, is_active, created_at)
                    VALUES(:id, :name, :bonus, 1, :created_at)
                    """
                ),
                {"id": next_id(conn, "tariffs"), "name": name, "bonus": bonus, "created_at": now_db()},
            )
            add_audit_safe(conn, "Тариф қўшилди", f"{name}; бонус={bonus}")
            flash("Тариф қўшилди.", "success")
        except IntegrityError as exc:
            flash(f"Тариф қўшишда база хатоси: {db_error_text(exc)}", "danger")
        except Exception as exc:
            flash(f"Тариф қўшишда хато: {db_error_text(exc)}", "danger")
    return redirect(url_for("tariffs"))


def sale_new_safe():
    if request.method == "POST":
        sale_date = request.form.get("sale_date", "").strip()
        employee_id = core.parse_int(request.form.get("employee_id"))
        comment = request.form.get("comment", "").strip()
        quantities, has_negative = core.collect_tariff_quantities(request.form)

        error = core.validate_daily_sale_form(sale_date, employee_id, quantities, has_negative)
        if error:
            flash(error, "danger")
            return redirect(url_for("sale_new", sale_date=sale_date, employee_id=employee_id))
        if core.is_month_closed(sale_date[:7]):
            flash("Бу ой ёпилган. Маълумот киритиш ёки ўзгартириш мумкин эмас.", "danger")
            return redirect(url_for("sale_new", sale_date=sale_date, employee_id=employee_id))

        inserted, updated = core.save_daily_sales(
            sale_date=sale_date,
            employee_id=employee_id,
            quantities=quantities,
            comment=comment,
            created_by=session.get("username", "admin"),
        )
        if inserted or updated:
            parts = []
            if inserted:
                parts.append(f"{inserted} та янги тариф")
            if updated:
                parts.append(f"{updated} та аввал киритилган тариф янгиланди")
            flash("Кунлик сотув сақланди: " + ", ".join(parts) + ".", "success")
            return redirect(url_for("sale_new", sale_date=sale_date))

        flash("Сақлаш учун мос тариф топилмади.", "warning")
        return redirect(url_for("sale_new", sale_date=sale_date, employee_id=employee_id))

    employees_list, tariffs_list = core.get_active_refs(positive_tariffs_only=True)
    selected_date = request.args.get("sale_date", "").strip() or datetime.today().date().isoformat()
    selected_employee_id = core.parse_int(request.args.get("employee_id"))
    return render_template(
        "sale_form.html",
        active="sale_new",
        sale=None,
        employees=employees_list,
        tariffs=tariffs_list,
        today=selected_date,
        selected_employee_id=selected_employee_id,
    )

app.view_functions["add_employee"] = add_employee_safe
app.view_functions["add_tariff"] = add_tariff_safe
app.view_functions["sale_new"] = sale_new_safe
