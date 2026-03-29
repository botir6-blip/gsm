from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func

from .extensions import db
from .models import (
    AuditLog,
    CarrierType,
    Company,
    FuelTransaction,
    OperationType,
    ProjectObject,
    SettlementEntry,
    StockEntry,
    User,
    Warehouse,
    as_dict_transaction,
)


OUR_COMPANY_FLAG = True


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None


def decimal_qty(value: str | Decimal | float | int) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.001"))
    return Decimal(str(value)).quantize(Decimal("0.001"))


OPERATION_LABELS = {
    OperationType.OPENING_BALANCE.value: "Очилиш қолдиғи",
    OperationType.REFINERY_RECEIPT.value: "Заводдан кирим",
    OperationType.ISSUE_TO_OBJECT.value: "Объектга чиқим",
    OperationType.WAREHOUSE_TRANSFER.value: "Складлар орасида ўтказиш",
    OperationType.THIRD_PARTY_PICKUP.value: "Компания ўз ёқилғисини олиб кетди",
    OperationType.LOAN_RECEIVED.value: "Қарзга олинди",
    OperationType.LOAN_GIVEN.value: "Қарзга берилди",
    OperationType.LOAN_REPAID_BY_US.value: "Қарз қайтарилди (биздан)",
    OperationType.LOAN_RETURNED_BY_COUNTERPARTY.value: "Қарз қайтарилди (улардан)",
    OperationType.ADJUSTMENT.value: "Тузатиш/корректировка",
}


CARRIER_LABELS = {
    CarrierType.WAGON.value: "Вагон",
    CarrierType.TANK_TRUCK.value: "Бензовоз",
    CarrierType.INTERNAL_TRANSFER.value: "Ички ўтказиш",
    CarrierType.MANUAL.value: "Қўлда",
}


def validate_transaction(tx: FuelTransaction) -> ValidationResult:
    qty = decimal_qty(tx.qty_kg)
    if qty <= 0:
        return ValidationResult(False, "Миқдор 0 дан катта бўлиши керак.")

    op = tx.operation_type

    if op in {
        OperationType.OPENING_BALANCE.value,
        OperationType.REFINERY_RECEIPT.value,
        OperationType.LOAN_RECEIVED.value,
        OperationType.LOAN_RETURNED_BY_COUNTERPARTY.value,
    } and not tx.dest_warehouse_id:
        return ValidationResult(False, "Кириш склади танланиши керак.")

    if op in {
        OperationType.ISSUE_TO_OBJECT.value,
        OperationType.THIRD_PARTY_PICKUP.value,
        OperationType.LOAN_GIVEN.value,
        OperationType.LOAN_REPAID_BY_US.value,
    } and not tx.source_warehouse_id:
        return ValidationResult(False, "Чиқиш склади танланиши керак.")

    if op == OperationType.WAREHOUSE_TRANSFER.value:
        if not tx.source_warehouse_id or not tx.dest_warehouse_id:
            return ValidationResult(False, "Иккала склад ҳам танланиши керак.")
        if tx.source_warehouse_id == tx.dest_warehouse_id:
            return ValidationResult(False, "Манба ва қабул қилувчи склад бир хил бўлмаслиги керак.")

    if op == OperationType.ISSUE_TO_OBJECT.value and not tx.object_id:
        return ValidationResult(False, "Объект танланиши керак.")

    if op in {
        OperationType.LOAN_RECEIVED.value,
        OperationType.LOAN_GIVEN.value,
        OperationType.LOAN_REPAID_BY_US.value,
        OperationType.LOAN_RETURNED_BY_COUNTERPARTY.value,
    } and not tx.counterparty_company_id:
        return ValidationResult(False, "Контрагент компания танланиши керак.")

    return ValidationResult(True)


def create_stock_entry(transaction_id: int, entry_date: date, warehouse_id: int, owner_company_id: int, qty_kg: Decimal, note: str) -> None:
    db.session.add(
        StockEntry(
            transaction_id=transaction_id,
            entry_date=entry_date,
            warehouse_id=warehouse_id,
            owner_company_id=owner_company_id,
            qty_kg=decimal_qty(qty_kg),
            note=note,
        )
    )


def create_settlement_entry(transaction_id: int, entry_date: date, counterparty_company_id: int, qty_kg: Decimal, note: str) -> None:
    db.session.add(
        SettlementEntry(
            transaction_id=transaction_id,
            entry_date=entry_date,
            counterparty_company_id=counterparty_company_id,
            qty_kg=decimal_qty(qty_kg),
            note=note,
        )
    )


def rebuild_derived_entries(tx: FuelTransaction) -> None:
    StockEntry.query.filter_by(transaction_id=tx.id).delete()
    SettlementEntry.query.filter_by(transaction_id=tx.id).delete()

    qty = decimal_qty(tx.qty_kg)
    label = OPERATION_LABELS.get(tx.operation_type, tx.operation_type)

    if tx.operation_type == OperationType.OPENING_BALANCE.value:
        create_stock_entry(tx.id, tx.doc_date, tx.dest_warehouse_id, tx.owner_company_id, qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.REFINERY_RECEIPT.value:
        create_stock_entry(tx.id, tx.doc_date, tx.dest_warehouse_id, tx.owner_company_id, qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.ISSUE_TO_OBJECT.value:
        create_stock_entry(tx.id, tx.doc_date, tx.source_warehouse_id, tx.owner_company_id, -qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.WAREHOUSE_TRANSFER.value:
        create_stock_entry(tx.id, tx.doc_date, tx.source_warehouse_id, tx.owner_company_id, -qty, f"{label}: {tx.doc_no}")
        create_stock_entry(tx.id, tx.doc_date, tx.dest_warehouse_id, tx.owner_company_id, qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.THIRD_PARTY_PICKUP.value:
        create_stock_entry(tx.id, tx.doc_date, tx.source_warehouse_id, tx.owner_company_id, -qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.LOAN_RECEIVED.value:
        create_stock_entry(tx.id, tx.doc_date, tx.dest_warehouse_id, tx.owner_company_id, qty, f"{label}: {tx.doc_no}")
        create_settlement_entry(tx.id, tx.doc_date, tx.counterparty_company_id, -qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.LOAN_GIVEN.value:
        create_stock_entry(tx.id, tx.doc_date, tx.source_warehouse_id, tx.owner_company_id, -qty, f"{label}: {tx.doc_no}")
        create_settlement_entry(tx.id, tx.doc_date, tx.counterparty_company_id, qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.LOAN_REPAID_BY_US.value:
        create_stock_entry(tx.id, tx.doc_date, tx.source_warehouse_id, tx.owner_company_id, -qty, f"{label}: {tx.doc_no}")
        create_settlement_entry(tx.id, tx.doc_date, tx.counterparty_company_id, qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.LOAN_RETURNED_BY_COUNTERPARTY.value:
        create_stock_entry(tx.id, tx.doc_date, tx.dest_warehouse_id, tx.owner_company_id, qty, f"{label}: {tx.doc_no}")
        create_settlement_entry(tx.id, tx.doc_date, tx.counterparty_company_id, -qty, f"{label}: {tx.doc_no}")

    elif tx.operation_type == OperationType.ADJUSTMENT.value:
        if tx.source_warehouse_id:
            create_stock_entry(tx.id, tx.doc_date, tx.source_warehouse_id, tx.owner_company_id, -qty, f"{label}: {tx.doc_no}")
        if tx.dest_warehouse_id:
            create_stock_entry(tx.id, tx.doc_date, tx.dest_warehouse_id, tx.owner_company_id, qty, f"{label}: {tx.doc_no}")


def add_audit_log(entity_name: str, entity_id: int, action: str, before_data: dict | None, after_data: dict | None, user_id: int) -> None:
    db.session.add(
        AuditLog(
            entity_name=entity_name,
            entity_id=entity_id,
            action=action,
            before_json=json.dumps(before_data, ensure_ascii=False, default=str) if before_data else None,
            after_json=json.dumps(after_data, ensure_ascii=False, default=str) if after_data else None,
            changed_by_id=user_id,
        )
    )


def transaction_payload_from_form(form) -> dict:
    def get_int(name: str) -> int | None:
        value = form.get(name)
        return int(value) if value else None

    return {
        "doc_no": (form.get("doc_no") or "").strip(),
        "doc_date": datetime.strptime(form.get("doc_date"), "%Y-%m-%d").date(),
        "operation_type": form.get("operation_type"),
        "qty_kg": decimal_qty(form.get("qty_kg") or "0"),
        "owner_company_id": int(form.get("owner_company_id")),
        "counterparty_company_id": get_int("counterparty_company_id"),
        "source_warehouse_id": get_int("source_warehouse_id"),
        "dest_warehouse_id": get_int("dest_warehouse_id"),
        "object_id": get_int("object_id"),
        "carrier_type": form.get("carrier_type") or CarrierType.MANUAL.value,
        "refinery_name": (form.get("refinery_name") or "").strip() or None,
        "comment": (form.get("comment") or "").strip() or None,
        "status": "posted",
    }


def create_transaction(payload: dict, user: User) -> FuelTransaction:
    tx = FuelTransaction(**payload, created_by_id=user.id, updated_by_id=user.id)
    validation = validate_transaction(tx)
    if not validation.ok:
        raise ValueError(validation.error)

    db.session.add(tx)
    db.session.flush()
    rebuild_derived_entries(tx)
    add_audit_log("fuel_transaction", tx.id, "create", None, as_dict_transaction(tx), user.id)
    db.session.commit()
    return tx


def update_transaction(tx: FuelTransaction, payload: dict, user: User) -> FuelTransaction:
    before = as_dict_transaction(tx)
    for key, value in payload.items():
        setattr(tx, key, value)
    tx.updated_by_id = user.id
    validation = validate_transaction(tx)
    if not validation.ok:
        raise ValueError(validation.error)

    rebuild_derived_entries(tx)
    add_audit_log("fuel_transaction", tx.id, "update", before, as_dict_transaction(tx), user.id)
    db.session.commit()
    return tx


def stock_balance_by_warehouse(as_of: date | None = None):
    query = (
        db.session.query(
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            Company.name.label("owner_company_name"),
            func.coalesce(func.sum(StockEntry.qty_kg), 0).label("balance_kg"),
        )
        .join(Warehouse, Warehouse.id == StockEntry.warehouse_id)
        .join(Company, Company.id == StockEntry.owner_company_id)
    )
    if as_of:
        query = query.filter(StockEntry.entry_date <= as_of)

    return (
        query.group_by(Warehouse.id, Warehouse.name, Company.name)
        .order_by(Warehouse.name.asc(), Company.name.asc())
        .all()
    )


def monthly_warehouse_report():
    min_date = db.session.query(func.min(StockEntry.entry_date)).scalar()
    if not min_date:
        return []

    today = date.today()
    month_cursor = date(min_date.year, min_date.month, 1)
    end_month = date(today.year, today.month, 1)

    results = []
    while month_cursor <= end_month:
        last_day = calendar.monthrange(month_cursor.year, month_cursor.month)[1]
        month_end = date(month_cursor.year, month_cursor.month, last_day)
        month_entries = (
            db.session.query(
                Warehouse.name.label("warehouse_name"),
                Company.name.label("owner_company_name"),
                func.coalesce(func.sum(StockEntry.qty_kg), 0).label("balance_kg"),
            )
            .join(Warehouse, Warehouse.id == StockEntry.warehouse_id)
            .join(Company, Company.id == StockEntry.owner_company_id)
            .filter(StockEntry.entry_date <= month_end)
            .group_by(Warehouse.name, Company.name)
            .having(func.coalesce(func.sum(StockEntry.qty_kg), 0) != 0)
            .order_by(Warehouse.name.asc(), Company.name.asc())
            .all()
        )
        for row in month_entries:
            results.append(
                {
                    "month": month_end.strftime("%Y-%m"),
                    "warehouse_name": row.warehouse_name,
                    "owner_company_name": row.owner_company_name,
                    "balance_kg": decimal_qty(row.balance_kg),
                }
            )
        if month_cursor.month == 12:
            month_cursor = date(month_cursor.year + 1, 1, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month + 1, 1)
    return results


def settlement_report():
    rows = (
        db.session.query(
            Company.name.label("company_name"),
            func.coalesce(func.sum(SettlementEntry.qty_kg), 0).label("net_qty_kg"),
        )
        .join(Company, Company.id == SettlementEntry.counterparty_company_id)
        .group_by(Company.name)
        .order_by(Company.name.asc())
        .all()
    )

    report = []
    for row in rows:
        net = decimal_qty(row.net_qty_kg)
        if net > 0:
            status = "Улар биздан қарз"
        elif net < 0:
            status = "Бизнинг улардан қарзимиз бор"
        else:
            status = "Ёпилган"
        report.append({
            "company_name": row.company_name,
            "net_qty_kg": net,
            "status": status,
        })
    return report


def dashboard_metrics():
    total_docs = FuelTransaction.query.count()
    total_companies = Company.query.count()
    total_warehouses = Warehouse.query.count()
    total_objects = ProjectObject.query.count()

    our_company_ids = [c.id for c in Company.query.filter_by(is_our_company=True).all()]
    our_stock = Decimal("0.000")
    if our_company_ids:
        stock_sum = (
            db.session.query(func.coalesce(func.sum(StockEntry.qty_kg), 0))
            .filter(StockEntry.owner_company_id.in_(our_company_ids))
            .scalar()
        )
        our_stock = decimal_qty(stock_sum)

    receivable = Decimal("0.000")
    payable = Decimal("0.000")
    for row in settlement_report():
        net = row["net_qty_kg"]
        if net > 0:
            receivable += net
        elif net < 0:
            payable += abs(net)

    return {
        "total_docs": total_docs,
        "total_companies": total_companies,
        "total_warehouses": total_warehouses,
        "total_objects": total_objects,
        "our_stock": our_stock,
        "receivable": receivable,
        "payable": payable,
    }


def seed_reference_data(default_our_company_name: str, admin_username: str, admin_password: str) -> None:
    if not User.query.filter_by(username=admin_username).first():
        admin = User(username=admin_username, full_name="Главный администратор", role="admin")
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.flush()
    else:
        admin = User.query.filter_by(username=admin_username).first()

    our_company = Company.query.filter_by(name=default_our_company_name).first()
    if not our_company:
        our_company = Company(name=default_our_company_name, is_our_company=True)
        db.session.add(our_company)
        db.session.flush()

    enter_company = Company.query.filter_by(name="Enter Engineering").first()
    if not enter_company:
        enter_company = Company(name="Enter Engineering", is_our_company=False)
        db.session.add(enter_company)
        db.session.flush()

    defaults = [
        ("ГСМ склад Карши (Жайхун)", our_company.id, "Карши"),
        ("ГСМ склад Кунград", our_company.id, "Кунград"),
        ("ГСМ склад Дарбанд", our_company.id, "Дарбанд"),
        ("ГСМ склад Кандым", our_company.id, "Кандым"),
        ("Enter склад 1", enter_company.id, "—"),
        ("Enter склад 2", enter_company.id, "—"),
    ]
    for name, host_company_id, city in defaults:
        if not Warehouse.query.filter_by(name=name).first():
            db.session.add(Warehouse(name=name, host_company_id=host_company_id, city=city))
    db.session.flush()

    opening_docs = {
        "OPEN-2023-001": ("ГСМ склад Карши (Жайхун)", Decimal("355461.000")),
        "OPEN-2023-002": ("ГСМ склад Кунград", Decimal("612861.000")),
        "OPEN-2023-003": ("ГСМ склад Дарбанд", Decimal("289259.000")),
        "OPEN-2023-004": ("ГСМ склад Кандым", Decimal("0.000")),
    }

    for doc_no, (warehouse_name, qty) in opening_docs.items():
        existing = FuelTransaction.query.filter_by(doc_no=doc_no).first()
        if existing:
            continue
        warehouse = Warehouse.query.filter_by(name=warehouse_name).first()
        tx = FuelTransaction(
            doc_no=doc_no,
            doc_date=date(2023, 1, 1),
            operation_type=OperationType.OPENING_BALANCE.value,
            qty_kg=qty,
            owner_company_id=our_company.id,
            dest_warehouse_id=warehouse.id,
            carrier_type=CarrierType.MANUAL.value,
            comment="Система бошланғич қолдиғи",
            status="posted",
            created_by_id=admin.id,
            updated_by_id=admin.id,
        )
        db.session.add(tx)
        db.session.flush()
        rebuild_derived_entries(tx)
        add_audit_log("fuel_transaction", tx.id, "create", None, as_dict_transaction(tx), admin.id)

    db.session.commit()
