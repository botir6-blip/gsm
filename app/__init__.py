from flask import Flask

from config import Config
from .extensions import db

# МОДЕЛЛАРНИ АЛБАТТА create_all() дан олдин импорт қилиш керак
from . import models

from .routes.audit import audit_bp
from .routes.auth import auth_bp
from .routes.companies import companies_bp
from .routes.main import main_bp
from .routes.objects import objects_bp
from .routes.transactions import transactions_bp
from .routes.warehouses import warehouses_bp
from .services import seed_reference_data


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        seed_reference_data(
            default_our_company_name=app.config["DEFAULT_OUR_COMPANY_NAME"],
            admin_username=app.config["DEFAULT_ADMIN_USERNAME"],
            admin_password=app.config["DEFAULT_ADMIN_PASSWORD"],
        )

    app.register_blueprint(auth_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(warehouses_bp)
    app.register_blueprint(objects_bp)
    app.register_blueprint(transactions_bp)

    return app
