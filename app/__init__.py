from flask import Flask
from sqlalchemy import text

from config import Config
from .extensions import db
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
        print("DB URI =", app.config["SQLALCHEMY_DATABASE_URI"], flush=True)
        print("TABLES BEFORE CREATE =", list(db.metadata.tables.keys()), flush=True)

        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("DB_PING_OK", flush=True)
        except Exception as e:
            import traceback
            print("DB_PING_ERROR =", repr(e), flush=True)
            traceback.print_exc()
            raise

        try:
            db.create_all()
            print("CREATE_ALL_OK", flush=True)
            print("TABLES AFTER CREATE =", list(db.metadata.tables.keys()), flush=True)
        except Exception as e:
            import traceback
            print("CREATE_ALL_ERROR =", repr(e), flush=True)
            traceback.print_exc()
            raise

        try:
            seed_reference_data(
                default_our_company_name=app.config["DEFAULT_OUR_COMPANY_NAME"],
                admin_username=app.config["DEFAULT_ADMIN_USERNAME"],
                admin_password=app.config["DEFAULT_ADMIN_PASSWORD"],
            )
            print("SEED_OK", flush=True)
        except Exception as e:
            import traceback
            print("SEED_ERROR =", repr(e), flush=True)
            traceback.print_exc()
            raise

    app.register_blueprint(auth_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(warehouses_bp)
    app.register_blueprint(objects_bp)
    app.register_blueprint(transactions_bp)

    return app
