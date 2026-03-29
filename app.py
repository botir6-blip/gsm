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
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
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
    if "art oil" in t:
        return "ART OIL TRANS"

    return text.strip()


def detect_delivery_type(text):
    if not text:
        return None

    t = text.lower()
    if "вагон" in t or "vagon" in t:
        return "wagon"
    if "бензовоз" in t or "benzovoz" in t:
        return "fuel_truck"
    if "авто" in t:
        return "fuel_truck"

    return None


def clean_col_name(text):
    return (
        str(text)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("ё", "е")
        .replace(".", "")
    )


def find_col(df, possible_names):
    normalized = {clean_col_name(c): c for c in df.columns}
    for name in possible_names:
        key = clean_col_name(name)
        if key in normalized:
            return normalized[key]
    return None


def row_joined_text(row_values):
    return " | ".join(
        [str(v).strip().lower() for v in row_values if pd.notna(v) and str(v).strip()]
    )


def load_receipt_sheet(xls, sheet_name):
    raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
    header_row = None

    for i in range(min(40, len(raw))):
        vals = [str(v).strip().lower() for v in raw.iloc[i].tolist() if pd.notna(v) and str(v).strip()]
        joined = " | ".join(vals)

        has_date = "дата" in joined
        has_doc = ("ттн" in joined) or ("акт" in joined) or ("№" in joined)
        has_volume = (
            "обьем/л" in joined
            or "объём/л" in joined
            or "объем/л" in joined
            or "литр" in joined
            or "обьем" in joined
            or "объем" in joined
        )

        if has_date and has_doc and has_volume:
            header_row = i
            break

    if header_row is None:
        # захира вариант: "дата" ва "объем" бор қаторни олади
        for i in range(min(40, len(raw))):
            vals = [str(v).strip().lower() for v in raw.iloc[i].tolist() if pd.notna(v) and str(v).strip()]
            joined = " | ".join(vals)
            if "дата" in joined and ("обьем" in joined or "объем" in joined or "литр" in joined):
                header_row = i
                break

    if header_row is None:
        return pd.DataFrame()

    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all")
    return df

def load_issue_sheet(xls, sheet_name):
    raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
    header_row = None

    for i in range(min(25, len(raw))):
        joined = row_joined_text(raw.iloc[i].tolist())
        if "дата" in joined and ("№ттн" in joined or "ттн" in joined) and "литр" in joined:
            header_row = i
            break

    if header_row is None:
        return pd.DataFrame()

    df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all")
    return df


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

        if lower_sheet.startswith("приход"):
            df = load_receipt_sheet(xls, sheet_name)
        else:
            df = load_issue_sheet(xls, sheet_name)

        if df.empty:
            continue

        date_col = find_col(df, ["Дата"])
        liters_col = find_col(df, ["обьем/л", "объём/л", "объем/л", "литр", "литры"])
        kg_col = find_col(df, ["Масса/кг", "кг"])
        doc_col = find_col(df, ["ТТН", "№ТТН", "№ ттн", "Номер ТТН", "Акт"])
        source_col = find_col(df, ["От куда", "Откуда"])
        dest_col = find_col(df, ["Куда отправлено", "Куда"])
        object_col = find_col(df, ["в какой объект", "Объект"])
        bb_col = find_col(df, ["№ б/б", "б/б", "№б/б"])
        field_col = find_col(df, ["Месторождения", "Месторождение"])
        density_col = find_col(df, ["Уд.вес", "Удельный вес", "плотность"])
        temp_col = find_col(df, ["Температура"])
        note_col = find_col(df, ["Примечание", "Примечания", "Изоҳ"])
        company_col = find_col(df, ["Столбец1", "Компания", "Организация"])

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

                note_text = normalize_text(row[note_col]) if note_col else None
                delivery_type = detect_delivery_type(note_text)
                comment = note_text

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
                comment = normalize_text(row[note_col]) if note_col else None

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
                "source_row": int(idx) + 1,
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
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                background: #f2f2f2;
            }
            .wrap {
                max-width: 1800px;
                margin: 0 auto;
                padding: 0;
            }
            .card {
                background: white;
                padding: 18px;
                border-radius: 14px;
                margin-bottom: 18px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            }
            h2, h3 {
                margin-top: 0;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                background: white;
            }
            th, td {
                border: 1px solid #ddd;
                padding: 10px 8px;
                font-size: 14px;
                text-align: center;
            }
            th {
                background: #f0f0f0;
            }
            .stats {
                display: flex;
                gap: 20px;
                flex-wrap: wrap;
            }
            .stat {
                padding: 14px 18px;
                background: #e9edf7;
                border-radius: 12px;
                min-width: 220px;
                font-size: 18px;
                font-weight: bold;
            }
            .flash {
                padding: 14px;
                border-radius: 10px;
                margin-bottom: 14px;
                background: #e8f5e9;
                font-size: 18px;
            }
            .upload-row {
                display: flex;
                gap: 12px;
                align-items: center;
                flex-wrap: wrap;
            }
            button {
                padding: 8px 16px;
                font-size: 16px;
                cursor: pointer;
            }
            input[type="file"] {
                font-size: 16px;
            }
        </style>
    </head>
    <body>
        <div class="wrap">
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
                    <div class="upload-row">
                        <input type="file" name="file" accept=".xlsx,.xls" required>
                        <button type="submit">Excel юклаш</button>
                    </div>
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


@app.route("/clear")
def clear_data():
    execute_query("DELETE FROM operations_simple")
    flash("База тозаланди")
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return {"ok": True}

@app.route("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    init_db()
