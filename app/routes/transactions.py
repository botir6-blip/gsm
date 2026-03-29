from decimal import Decimal

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..models import Company, FuelTransaction, ProjectObject, Warehouse
from ..services import (
    CARRIER_LABELS,
    OPERATION_LABELS,
    create_transaction,
    monthly_warehouse_report,
    settlement_report,
    transaction_payload_from_form,
    update_transaction,
)
from .auth import login_required


transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@transactions_bp.route("/")
@login_required
def list_transactions():
    operation_type = request.args.get("operation_type")
    company_id = request.args.get("company_id", type=int)
    query = FuelTransaction.query
    if operation_type:
        query = query.filter_by(operation_type=operation_type)
    if company_id:
        query = query.filter_by(owner_company_id=company_id)
    transactions = query.order_by(FuelTransaction.doc_date.desc(), FuelTransaction.id.desc()).all()
    companies = Company.query.order_by(Company.name.asc()).all()
    return render_template(
        "transactions.html",
        transactions=transactions,
        companies=companies,
        operation_labels=OPERATION_LABELS,
        carrier_labels=CARRIER_LABELS,
        selected_operation_type=operation_type,
        selected_company_id=company_id,
    )


@transactions_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_transaction_view():
    companies = Company.query.order_by(Company.name.asc()).all()
    warehouses = Warehouse.query.order_by(Warehouse.name.asc()).all()
    objects = ProjectObject.query.order_by(ProjectObject.name.asc()).all()
    if request.method == "POST":
        try:
            payload = transaction_payload_from_form(request.form)
            create_transaction(payload, g.user)
            flash("Ҳужжат сақланди ва проводка қилинди.", "success")
            return redirect(url_for("transactions.list_transactions"))
        except Exception as exc:
            flash(str(exc), "danger")
    return render_template(
        "transaction_form.html",
        tx=None,
        companies=companies,
        warehouses=warehouses,
        objects=objects,
        operation_labels=OPERATION_LABELS,
        carrier_labels=CARRIER_LABELS,
    )


@transactions_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(tx_id: int):
    tx = FuelTransaction.query.get_or_404(tx_id)
    companies = Company.query.order_by(Company.name.asc()).all()
    warehouses = Warehouse.query.order_by(Warehouse.name.asc()).all()
    objects = ProjectObject.query.order_by(ProjectObject.name.asc()).all()

    if request.method == "POST":
        try:
            payload = transaction_payload_from_form(request.form)
            update_transaction(tx, payload, g.user)
            flash("Ҳужжат янгиланди. Аудит журналига ёзилди.", "success")
            return redirect(url_for("transactions.list_transactions"))
        except Exception as exc:
            flash(str(exc), "danger")

    return render_template(
        "transaction_form.html",
        tx=tx,
        companies=companies,
        warehouses=warehouses,
        objects=objects,
        operation_labels=OPERATION_LABELS,
        carrier_labels=CARRIER_LABELS,
    )


@transactions_bp.route("/monthly-balances")
@login_required
def monthly_balances():
    rows = monthly_warehouse_report()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["month"], []).append(row)
    return render_template("monthly_balances.html", grouped=grouped)


@transactions_bp.route("/settlements")
@login_required
def settlements():
    return render_template("settlements.html", rows=settlement_report())
