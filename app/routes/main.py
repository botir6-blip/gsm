from flask import Blueprint, render_template

from ..services import dashboard_metrics, settlement_report, stock_balance_by_warehouse
from .auth import login_required


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        metrics=dashboard_metrics(),
        stock_rows=stock_balance_by_warehouse(),
        settlement_rows=settlement_report(),
    )
