# Ledger API

Бэкенд сервиса для личных задач и планирования, а также совместной работы над проектами.

Задачу или проект можно создать отдельно или назначить одному
или нескольким исполнителям добавленным в контакты. Каждый исполнитель отмечает выполнение
своей части работы. Задачу целиком принимает и закрывает владелец.

Права участников проекта определяются ролями `owner`, `editor` и `viewer`.

В сервисе также есть календарь, планы, заметки и файловые вложения.

## Стек

- Python, FastAPI, Pydantic
- PostgreSQL, SQLAlchemy, Alembic
- pytest, HTTPX

## Локальный запуск

Для запуска нужны Python и PostgreSQL. Команды ниже приведены для PowerShell.

Из корня репозитория:

1. Создать виртуальное окружение и установить зависимости:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

2. Создайть пустую базу PostgreSQL. Скопировать `.env.example` в `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

   В `.env` задать параметры подключения: `DB_HOST`, `DB_PORT`, `DB_USER`,
   `DB_PASS` и `DB_NAME`. Собственный `SECRET_KEY` для подписи токенов

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Запустить миграции и API:

   ```powershell
   alembic upgrade head
   uvicorn src.main:app --reload
   ```

   Документация API будет доступна по адресу http://127.0.0.1:8000/docs.
