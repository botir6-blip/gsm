from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Role(str, Enum):
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    OPERATOR = "operator"
    VIEWER = "viewer"


class OperationType(str, Enum):
    OPENING_BALANCE = "opening_balance"
    REFINERY_RECEIPT = "refinery_receipt"
    ISSUE_TO_OBJECT = "issue_to_object"
    WAREHOUSE_TRANSFER = "warehouse_transfer"
    THIRD_PARTY_PICKUP = "third_party_pickup"
    LOAN_RECEIVED = "loan_received"
    LOAN_GIVEN = "loan_given"
    LOAN_REPAID_BY_US = "loan_repaid_by_us"
    LOAN_RETURNED_BY_COUNTERPARTY = "loan_returned_by_counterparty"
    ADJUSTMENT = "adjustment"


class CarrierType(str, Enum):
    WAGON = "wagon"
    TANK_TRUCK = "tank_truck"
    INTERNAL_TRANSFER = "internal_transfer"
    MANUAL = "manual"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=Role.ADMIN.value)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    is_our_company = db.Column(db.Boolean, nullable=False, default=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Warehouse(db.Model):
    __tablename__ = "warehouses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    host_company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    city = db.Column(db.String(120))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    host_company = db.relationship("Company")


class ProjectObject(db.Model):
    __tablename__ = "project_objects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    project_name = db.Column(db.String(180))
    region = db.Column(db.String(120))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    company = db.relationship("Company")


class FuelTransaction(db.Model):
    __tablename__ = "fuel_transactions"

    id = db.Column(db.Integer, primary_key=True)
    doc_no = db.Column(db.String(80), nullable=False)
    doc_date = db.Column(db.Date, nullable=False, index=True)
    operation_type = db.Column(db.String(50), nullable=False, index=True)
    qty_kg = db.Column(db.Numeric(18, 3), nullable=False)
    owner_company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    counterparty_company_id = db.Column(db.Integer, db.ForeignKey("companies.id"))
    source_warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"))
    dest_warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"))
    object_id = db.Column(db.Integer, db.ForeignKey("project_objects.id"))
    carrier_type = db.Column(db.String(40), nullable=False, default=CarrierType.MANUAL.value)
    refinery_name = db.Column(db.String(120))
    comment = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="posted", index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner_company = db.relationship("Company", foreign_keys=[owner_company_id])
    counterparty_company = db.relationship("Company", foreign_keys=[counterparty_company_id])
    source_warehouse = db.relationship("Warehouse", foreign_keys=[source_warehouse_id])
    dest_warehouse = db.relationship("Warehouse", foreign_keys=[dest_warehouse_id])
    project_object = db.relationship("ProjectObject", foreign_keys=[object_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])


class StockEntry(db.Model):
    __tablename__ = "stock_entries"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("fuel_transactions.id"), nullable=False, index=True)
    entry_date = db.Column(db.Date, nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False, index=True)
    owner_company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    qty_kg = db.Column(db.Numeric(18, 3), nullable=False)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    transaction = db.relationship("FuelTransaction")
    warehouse = db.relationship("Warehouse")
    owner_company = db.relationship("Company")


class SettlementEntry(db.Model):
    __tablename__ = "settlement_entries"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("fuel_transactions.id"), nullable=False, index=True)
    entry_date = db.Column(db.Date, nullable=False, index=True)
    counterparty_company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    qty_kg = db.Column(db.Numeric(18, 3), nullable=False)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    transaction = db.relationship("FuelTransaction")
    counterparty_company = db.relationship("Company")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    entity_name = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)
    before_json = db.Column(db.Text)
    after_json = db.Column(db.Text)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    changed_by = db.relationship("User")


def as_dict_transaction(tx: FuelTransaction) -> dict:
    return {
        "id": tx.id,
        "doc_no": tx.doc_no,
        "doc_date": tx.doc_date.isoformat() if tx.doc_date else None,
        "operation_type": tx.operation_type,
        "qty_kg": str(tx.qty_kg or Decimal("0")),
        "owner_company_id": tx.owner_company_id,
        "counterparty_company_id": tx.counterparty_company_id,
        "source_warehouse_id": tx.source_warehouse_id,
        "dest_warehouse_id": tx.dest_warehouse_id,
        "object_id": tx.object_id,
        "carrier_type": tx.carrier_type,
        "refinery_name": tx.refinery_name,
        "comment": tx.comment,
        "status": tx.status,
    }
