from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from ..models import User


auth_bp = Blueprint("auth", __name__)


@auth_bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = User.query.get(user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Логин ёки парол хато.", "danger")
        elif not user.is_active:
            flash("Фойдаланувчи фаол эмас.", "danger")
        else:
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
