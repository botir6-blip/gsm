import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-please")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///gsm_audit.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_TITLE = os.environ.get("APP_TITLE", "ГСМ аудит ва склад ҳисоби")
    DEFAULT_ADMIN_USERNAME = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123")
    DEFAULT_OUR_COMPANY_NAME = os.environ.get("DEFAULT_OUR_COMPANY_NAME", "Наша компания (ERIELL)")
