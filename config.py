import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-please")

    database_url = os.environ.get("DATABASE_URL", "sqlite:///gsm_audit.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": 5},
    }

    APP_TITLE = os.environ.get("APP_TITLE", "ГСМ аудит ва склад ҳисоби")
    DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")
    DEFAULT_OUR_COMPANY_NAME = os.environ.get("DEFAULT_OUR_COMPANY_NAME", "Наша компания (ERIELL)")
