# ГСМ аудит ва склад ҳисоби

Бу Flask асосидаги веб-дастур дизель ёқилғи ҳаракатини аудит даражасида ҳисобга олиш учун тайёрланган.

## Нима қилади

- бир нечта компаниялар ёқилғисини бир неча складда юритади;
- бизнинг складларда бошқа компаниялар ёқилғисини сақлайди;
- бизнинг ёқилғимизни Enter каби ташқи складларда сақлайди;
- объектларга чиқимни ҳисобга олади;
- складлар орасида ўтказишларни юритади;
- кимдан қанча қарз олганмиз ёки ким биздан қарз эканини ҳисоблайди;
- ҳар бир склад бўйича ойлик қолдиқни кўрсатади;
- ҳужжат таҳрир қилинса, аудит журналига ёзади ва проводкаларни қайта қуриб беради.

## Бошланғич қолдиқлар (01.01.2023)

- ГСМ склад Карши (Жайхун): 355461 кг
- ГСМ склад Кунград: 612861 кг
- ГСМ склад Дарбанд: 289259 кг
- ГСМ склад Кандым: 0 кг

## Ўрнатиш

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Environment

```bash
export SECRET_KEY="super-secret"
export DATABASE_URL="sqlite:///gsm_audit.db"
export DEFAULT_ADMIN_USERNAME="admin"
export DEFAULT_ADMIN_PASSWORD="admin123"
export DEFAULT_OUR_COMPANY_NAME="Наша компания (ERIELL)"
```

PostgreSQL учун мисол:

```bash
export DATABASE_URL="postgresql+psycopg2://user:password@host:5432/dbname"
```

## Асосий операция турлари

- opening_balance — очилиш қолдиғи
- refinery_receipt — заводдан кирим
- issue_to_object — объектга чиқим
- warehouse_transfer — складлар орасида ўтказиш
- third_party_pickup — контрагент ўз ёқилғисини олиб кетиши
- loan_received — қарзга олинди
- loan_given — қарзга берилди
- loan_repaid_by_us — биз томондан қарз қайтарилди
- loan_returned_by_counterparty — улар томондан қарз қайтарилди
- adjustment — корректировка

## Мухим ғоя

Дастурда `fuel_transactions` — ҳужжатнинг ўзи,
`stock_entries` — склад кесимида ҳаракат,
`settlement_entries` — қарз/сальдо ҳаракати.

Шунинг учун бир ҳужжат ўзгартирилса, қолдиқ ва қарз қайта ҳисобланади.
