from flask import Blueprint, render_template

from ..models import AuditLog
from .auth import login_required


audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


@audit_bp.route("/")
@login_required
def list_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(300).all()
    return render_template("audit_logs.html", logs=logs)
