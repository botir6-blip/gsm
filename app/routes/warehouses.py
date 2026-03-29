from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Company, Warehouse
from .auth import login_required


warehouses_bp = Blueprint("warehouses", __name__, url_prefix="/warehouses")


@warehouses_bp.route("/")
@login_required
def list_warehouses():
    warehouses = Warehouse.query.order_by(Warehouse.name.asc()).all()
    companies = Company.query.order_by(Company.name.asc()).all()
    return render_template("warehouses.html", warehouses=warehouses, companies=companies)


@warehouses_bp.route("/create", methods=["POST"])
@login_required
def create_warehouse():
    name = (request.form.get("name") or "").strip()
    host_company_id = request.form.get("host_company_id")
    city = (request.form.get("city") or "").strip() or None
    note = (request.form.get("note") or "").strip() or None
    if not name or not host_company_id:
        flash("Склад номи ва эгаси танланиши шарт.", "danger")
    elif Warehouse.query.filter_by(name=name).first():
        flash("Бундай склад аллақачон бор.", "warning")
    else:
        db.session.add(Warehouse(name=name, host_company_id=int(host_company_id), city=city, note=note))
        db.session.commit()
        flash("Склад сақланди.", "success")
    return redirect(url_for("warehouses.list_warehouses"))
