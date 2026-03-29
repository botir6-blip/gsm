from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Company
from .auth import login_required


companies_bp = Blueprint("companies", __name__, url_prefix="/companies")


@companies_bp.route("/")
@login_required
def list_companies():
    companies = Company.query.order_by(Company.name.asc()).all()
    return render_template("companies.html", companies=companies)


@companies_bp.route("/create", methods=["POST"])
@login_required
def create_company():
    name = (request.form.get("name") or "").strip()
    is_our_company = request.form.get("is_our_company") == "1"
    note = (request.form.get("note") or "").strip() or None
    if not name:
        flash("Компания номи киритилиши керак.", "danger")
    elif Company.query.filter_by(name=name).first():
        flash("Бундай компания аллақачон мавжуд.", "warning")
    else:
        db.session.add(Company(name=name, is_our_company=is_our_company, note=note))
        db.session.commit()
        flash("Компания сақланди.", "success")
    return redirect(url_for("companies.list_companies"))
