from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Company, ProjectObject
from .auth import login_required


objects_bp = Blueprint("objects", __name__, url_prefix="/objects")


@objects_bp.route("/")
@login_required
def list_objects():
    company_id = request.args.get("company_id", type=int)
    query = ProjectObject.query
    if company_id:
        query = query.filter_by(company_id=company_id)
    objects = query.order_by(ProjectObject.name.asc()).all()
    companies = Company.query.order_by(Company.name.asc()).all()
    return render_template("objects.html", objects=objects, companies=companies, selected_company_id=company_id)


@objects_bp.route("/create", methods=["POST"])
@login_required
def create_object():
    name = (request.form.get("name") or "").strip()
    company_id = request.form.get("company_id")
    project_name = (request.form.get("project_name") or "").strip() or None
    region = (request.form.get("region") or "").strip() or None
    note = (request.form.get("note") or "").strip() or None

    if not name or not company_id:
        flash("Объект номи ва компания танланиши керак.", "danger")
    else:
        db.session.add(
            ProjectObject(
                name=name,
                company_id=int(company_id),
                project_name=project_name,
                region=region,
                note=note,
            )
        )
        db.session.commit()
        flash("Объект сақланди.", "success")
    return redirect(url_for("objects.list_objects"))
