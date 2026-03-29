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
            COALESCE(SUM(CASE WHEN operation_type = 'receipt' THEN kilograms ELSE 0 END), 0) AS total_receipt_kg,
            COALESCE(SUM(CASE WHEN operation_type = 'issue' THEN kilograms ELSE 0 END), 0) AS total_issue_kg,
            COALESCE(SUM(CASE WHEN operation_type = 'receipt' THEN kilograms ELSE 0 END), 0)
            - COALESCE(SUM(CASE WHEN operation_type = 'issue' THEN kilograms ELSE 0 END), 0) AS balance_kg
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
                min-width: 260px;
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
                <h3>Қисқача ҳисоб (КГ)</h3>
                <div class="stats">
                    <div class="stat"><strong>Жами кирим (кг):</strong><br>{{ stats.total_receipt_kg }}</div>
                    <div class="stat"><strong>Жами чиқим (кг):</strong><br>{{ stats.total_issue_kg }}</div>
                    <div class="stat"><strong>Соф қолдиқ (кг):</strong><br>{{ stats.balance_kg }}</div>
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
                            <th>Кг</th>
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
                            <td>{{ row.kilograms or "" }}</td>
                            <td>{{ row.liters or "" }}</td>
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
