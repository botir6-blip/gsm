# SIM Бонус — онлайн версия

Бу версия интернет орқали ишлашга тайёрланган. 1 та масъул одам кириб, ходимлар бўйича тариф ва сотилган SIM сонини киритади. Ой охирида бонус ҳисоботи ва Excel чиқади.

## Ичидаги функциялар

- Ўзбекча интерфейс, кириллда
- Ходимлар рўйхати
- Тарифлар рўйхати
- Кунлик сотув киритиш
- Сотувлар журнали
- Ойлик бонус ҳисоботи
- Excel экспорт
- Ойни ёпиш / қайта очиш
- Ўзгаришлар журнали
- Онлайн PostgreSQL базада сақлаш
- Локал ишлатганда SQLite базада сақлаш

## Кириш

Биринчи кириш:

```text
Логин: admin
Пароль: admin123
```

Киргандан кейин дарҳол паролни алмаштиринг.

## Railway’га қўйиш тартиби

1. Бу папкани GitHub repository’га юкланг.
2. Railway’да New Project очинг.
3. Deploy from GitHub repo танланг.
4. Шу repository’ни танланг.
5. Railway project ичида PostgreSQL database қўшинг.
6. App service variables ичида `DATABASE_URL` PostgreSQL билан боғланганига ишонч ҳосил қилинг.
7. App service variables ичида `SECRET_KEY` қўшинг. Узун махфий текст бўлсин.
8. Deploy қилинг.
9. Networking бўлимидан Public Domain / Generate Domain қилинг.
10. Берилган HTTPS ссылка орқали киринг.

## Start command

Procfile ичида тайёр:

```text
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

Агар Railway start command сўраса, шуни қўйинг:

```text
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

## Маълумотлар қаерда сақланади?

Онлайнда `DATABASE_URL` бор бўлса, ҳамма маълумот PostgreSQL базада сақланади. Шунинг учун Railway’да PostgreSQL қўшиш шарт.

Локалда `DATABASE_URL` бўлмаса, `sim_bonus.db` SQLite файлида сақланади.

## Локал текшириш

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Кейин браузерда:

```text
http://127.0.0.1:5000
```


## Компьютер ва Android учун илова режими

Бу версия PWA қилиб тайёрланган. Railway HTTPS доменини очгандан кейин Chrome/Edge орқали “Install app” ёки “Add to Home screen” қилиб компьютер ва Android телефонга илова иконкаси сифатида ўрнатиш мумкин. Батафсил: `README_APP_WINDOWS_ANDROID_UZ.md`.
