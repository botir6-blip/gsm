import os
from datetime import datetime
from io import BytesIO

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect, url_for, render_template_string, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL topilmadi")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def execute_query(query, params=None, fetch=False, many=False):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                if many:
                    cur.executemany(query, params)
                else:
                    cur.execute(query, params)
                if fetch:
                    return cur.fetchall()
    finally:
        conn.close()


def init_db():
    query = """
    CREATE TABLE IF NOT EXISTS operations_simple (
        id SERIAL PRIMARY KEY,
        operation_type VARCHAR(20) NOT NULL,
        operation_date DATE NOT NULL,
        doc_number VARCHAR(100),
        source_name VARCHAR(200),
        destination_name VARCHAR(200),
        warehouse_name VARCHAR(200),
        receiver_name VARCHAR(200),
        owner_company_name VARCHAR(150),
        accountable_company_name VARCHAR(150),
        supplier_name VARCHAR(150),
        delivery_type VARCHAR(30),
        bb_number VARCHAR(100),
        field_name VARCHAR(150),
        liters NUMERIC(14,2) NOT NULL DEFAULT 0,
        kilograms NUMERIC(14,2),
        density NUMERIC(10,4),
        temperature NUMERIC(10,2),
        comment TEXT,
        source_file VARCHAR(255),
        source_sheet VARCHAR(100),
        source_row INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    execute_query(query)


def normalize_text(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize_date(value):
    if pd.isna(value):
        return None

    if isinstance(value, datetime):
        return value.date()

    try:
        return pd.to_datetime(value, dayfirst=True, errors="coerce").date()
    except Exception:
        return None


def normalize_number(value):
    if pd.isna(value):
        return None
    try:
        text = str(value).replace(" ", "").replace(",", ".")
        return float(text)
    except Exception:
        return None


def detect_company(text):
    if not text:
        return None

    t = text.lower()

    if "eriell" in t:
        return "ERIELL"
    if "enter" in t:
        return "Enter Engineering"
    if "ems" in t:
        return "EMS"
    if "saneg" in t:
        return "SANEG"

    return text.strip()


def detect_delivery_type(text):
    if not text:
        return None

    t = text.lower()
    if "вагон" in t or "vagon" in t:
        return "wagon"
    if "бензовоз" in t or "benzovoz" in t:
        return "fuel_truck"

    return None


def find_col(df, possible_names):
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in possible_names:
        key = name.strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None


def import_sheet(file_bytes, source_file_name):
    xls = pd.ExcelFile(BytesIO(file_bytes))
    inserted_count = 0

    insert_sql = """
    INSERT INTO operations_simple (
        operation_type,
        operation_date,
        doc_number,
        source_name,
        destination_name,
        warehouse_name,
        receiver_name,
        owner_company_name,
        accountable_company_name,
        supplier_name,
        delivery_type,
        bb_number,
        field_name,
        liters,
        kilograms,
        density,
        temperature,
        comment,
        source_file,
        source_sheet,
        source_row
    )
    VALUES (
        %(operation_type)s,
        %(operation_date)s,
        %(doc_number)s,
        %(source_name)s,
        %(destination_name)s,
        %(warehouse_name)s,
        %(receiver_name)s,
        %(owner_company_name)s,
        %(accountable_company_name)s,
        %(supplier_name)s,
        %(delivery_type)s,
        %(bb_number)s,
        %(field_name)s,
        %(liters)s,
        %(kilograms)s,
        %(density)s,
        %(temperature)s,
        %(comment)s,
        %(source_file)s,
        %(source_sheet)s,
        %(source_row)s
    )
    """

    rows_to_insert = []

    for sheet_name in xls.sheet_names:
        lower_sheet = sheet_name.strip().lower()

        if not (lower_sheet.startswith("приход") or lower_sheet.startswith("расход")):
            continue

        df = pd.read_excel(xls, sheet_name=sheet_name)
        df.columns = [str(c).strip() for c in df.columns]

        if df.empty:
            continue

        date_col = find_col(df, ["Дата", "дата"])
        liters_col = find_col(df, ["обьем/л", "объём/л", "литр", "литры", "Литр"])
        kg_col = find_col(df, ["Масса/кг", "кг", "Кг"])
        doc_col = find_col(df, ["ТТН", "№ТТН", "№ ттн", "Номер ТТН"])
        source_col = find_col(df, ["От куда", "Откуда"])
        dest_col = find_col(df, ["Куда отправлено", "Куда"])
        object_col = find_col(df, ["в какой объект", "Объект"])
        bb_col = find_col(df, ["№ б/б", "б/б", "№б/б"])
        field_col = find_col(df, ["Месторождения", "Месторождение"])
        density_col = find_col(df, ["Уд.вес", "Удельный вес"])
        temp_col = find_col(df, ["Температура"])
        note_col = find_col(df, ["Примечание", "Примечания", "Изоҳ"])
        company_col = find_col(df, ["Столбец1", "Компания"])

        for idx, row in df.iterrows():
            operation_date = normalize_date(row[date_col]) if date_col else None
            liters = normalize_number(row[liters_col]) if liters_col else None

            if not operation_date or liters is None:
                continue

            if lower_sheet.startswith("приход"):
                operation_type = "receipt"
                source_name = normalize_text(row[source_col]) if source_col else None
                destination_name = "ГСМ склад Дарбанд"
                warehouse_name = "ГСМ склад Дарбанд"
                receiver_name = "ГСМ склад Дарбанд"

                raw_company = normalize_text(row[company_col]) if company_col else None
                owner_company_name = detect_company(raw_company)
                accountable_company_name = owner_company_name

                supplier_name = source_name
                delivery_type = detect_delivery_type(normalize_text(row[note_col]) if note_col else None)
                comment = normalize_text(row[note_col]) if note_col else None

            else:
                operation_type = "issue"
                source_name = "ГСМ склад Дарбанд"
                destination_name = normalize_text(row[dest_col]) if dest_col else None
                warehouse_name = "ГСМ склад Дарбанд"
                receiver_name = normalize_text(row[object_col]) if object_col else destination_name

                owner_company_name = detect_company(destination_name)
                accountable_company_name = owner_company_name

                supplier_name = None
                delivery_type = "fuel_truck"
                comment = None

            rows_to_insert.append({
                "operation_type": operation_type,
                "operation_date": operation_date,
                "doc_number": normalize_text(row[doc_col]) if doc_col else None,
                "source_name": source_name,
                "destination_name": destination_name,
                "warehouse_name": warehouse_name,
                "receiver_name": receiver_name,
                "owner_company_name": owner_company_name,
                "accountable_company_name": accountable_company_name,
                "supplier_name": supplier_name,
                "delivery_type": delivery_type,
                "bb_number": normalize_text(row[bb_col]) if bb_col else None,
                "field_name": normalize_text(row[field_col]) if field_col else None,
                "liters": liters,
                "kilograms": normalize_number(row[kg_col]) if kg_col else None,
                "density": normalize_number(row[density_col]) if density_col else None,
                "temperature": normalize_number(row[temp_col]) if temp_col else None,
                "comment": comment,
                "source_file": source_file_name,
                "source_sheet": sheet_name,
                "source_row": int(idx) + 2,
            })

    if rows_to_insert:
        execute_query(insert_sql, rows_to_insert, many=True)
        inserted_count = len(rows_to_insert)

    return inserted_count


@app.route("/")
def index():
    rows = execute_query("""
        SELECT
            id,
            operation_type,
            operation_date,
            doc_number,
            source_name,
            destination_name,
            warehouse_name,
            receiver_name,
            owner_company_name,
            liters,
            kilograms,
            source_sheet
        FROM operations_simple
        ORDER BY operation_date DESC, id DESC
        LIMIT 100
    """, fetch=True)

    stats = execute_query("""
        SELECT
            COALESCE(SUM(CASE WHEN operation_type = 'receipt' THEN liters ELSE 0 END), 0) AS total_receipt,
            COALESCE(SUM(CASE WHEN operation_type = 'issue' THEN liters ELSE 0 END), 0) AS total_issue,
            COALESCE(SUM(CASE WHEN operation_type = 'receipt' THEN liters ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN operation_type = 'issue' THEN liters ELSE 0 END), 0) AS balance
        FROM operations_simple
    """, fetch=True)[0]

    html = """
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <title>ГСМ Импорт</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 24px; background: #f7f7f7; }
            .card { background: white; padding: 16px; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
            table { width: 100%; border-collapse: collapse; background: white; }
            th, td { border: 1px solid #ddd; padding: 8px; font-size: 14px; }
            th { background: #f0f0f0; }
            .stats { display: flex; gap: 16px; flex-wrap: wrap; }
            .stat { padding: 12px 16px; background: #eef3ff; border-radius: 10px; min-width: 180px; }
            .flash { padding: 12px; border-radius: 8px; margin-bottom: 12px; background: #e8f5e9; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>ГСМ реестр импорт</h2>
            {% with messages = get_flashed_messages() %}
              {% if messages %}
                {% for msg in messages %}
                  <div class="flash">{{ msg }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}

            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept=".xlsx,.xls" required>
                <button type="submit">Excel юклаш</button>
            </form>
        </div>

        <div class="card">
            <h3>Қисқача ҳисоб</h3>
            <div class="stats">
                <div class="stat"><strong>Жами кирим:</strong><br>{{ stats.total_receipt }}</div>
                <div class="stat"><strong>Жами чиқим:</strong><br>{{ stats.total_issue }}</div>
                <div class="stat"><strong>Соф қолдиқ:</strong><br>{{ stats.balance }}</div>
            </div>
        </div>

        <div class="card">
            <h3>Охирги 100 операция</h3>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Сана</th>
                        <th>Тури</th>
                        <th>Ҳужжат</th>
                        <th>Қаердан</th>
                        <th>Қаерга</th>
                        <th>Компания</th>
                        <th>Литр</th>
                        <th>Лист</th>
                    </tr>
                </thead>
                <tbody>
                {% for row in rows %}
                    <tr>
                        <td>{{ row.id }}</td>
                        <td>{{ row.operation_date }}</td>
                        <td>{{ row.operation_type }}</td>
                        <td>{{ row.doc_number or "" }}</td>
                        <td>{{ row.source_name or "" }}</td>
                        <td>{{ row.destination_name or "" }}</td>
                        <td>{{ row.owner_company_name or "" }}</td>
                        <td>{{ row.liters }}</td>
                        <td>{{ row.source_sheet or "" }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, rows=rows, stats=stats)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Файл танланмаган")
        return redirect(url_for("index"))

    try:
        file_bytes = file.read()
        inserted = import_sheet(file_bytes, file.filename)
        flash(f"Муваффақиятли импорт қилинди: {inserted} қатор")
    except Exception as e:
        flash(f"Хато: {e}")

    return redirect(url_for("index"))


@app.route("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    init_db()
