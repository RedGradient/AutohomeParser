# Команды Makefile

Makefile загружает переменные из локального `.env`. По умолчанию используется
`compose.dev.yaml`; production-файл задаётся через
`COMPOSE_FILE=compose.prod.yaml`.

Актуальный список доступен командой:

```bash
make help
```

## Проверки и тесты

- `make lint` — Ruff check и проверка форматирования.
- `make lint-fix` — автоисправление и форматирование Ruff.
- `make pre-commit-install` — установить Git pre-commit hook.
- `make test-db-up` — поднять отдельный PostgreSQL для тестов.
- `make test` — запустить `unittest` с тестовой PostgreSQL.
- `make test-db-down` — удалить тестовый контейнер и volume.

## Сервисы

- `make postgres-up` — запустить PostgreSQL.
- `make database-migrate` — применить `alembic upgrade head`.
- `make api-up` — собрать и запустить API, PostgreSQL, Redis и Celery.
- `make api-run` — локально запустить Uvicorn из `.venv`.
- `make api-logs` — следить за логами API.
- `make celery-logs` — следить за Celery worker и beat.
- `make docker-down` — остановить Compose-проект без удаления volume.

Production-запуск:

```bash
make COMPOSE_FILE=compose.prod.yaml api-up
```

## Парсер

- `make parser-run` — полный многопроцессный обход в Docker.
- `make parser-resume` — дозагрузка отсутствующих конфигураций и задач.

Для `parser-run` и `parser-resume` задайте `AUTOHOME_INTERFACES` в `.env`.
Подробности: [`scrapy.md`](scrapy.md).

## Сеть

- `make network-up` — создать временные policy-routing rules.
- `make network-test` — проверить маршруты и внешние IP интерфейсов.
- `make network-status` — показать адреса, правила и routing tables.
- `make network-down` — удалить правила проекта.

Команды требуют переменные `WIFI_IF` и `ETH_IF`. Это исторические имена двух
маршрутов в Makefile: фактически в них можно указать любые разные сетевые
интерфейсы с IPv4-адресами. Пример:

```bash
make WIFI_IF=wlan0 ETH_IF=eth0 network-up
```

## Данные и постобработка

- `make database-reset` — удалить БД и заново применить миграции; команда
  требует ручного подтверждения.
- `make parameters-reset` — пересоздать таблицы характеристик.
- `make build-modifications` — нормализовать силовые установки и собрать
  модификации.
- `make normalize-vehicle-attributes` — обновить кузовные и массовые признаки.
- `make translate-db` — перевести существующие нормализованные поля.
- `make calculate-customs-payments` — пересчитать таможенные платежи.

Дополнительные аргументы передаются переменными:

```bash
make calculate-customs-payments \
  CALCULATE_CUSTOMS_PAYMENTS_ARGS="--mode stale --limit 100"
```

## Аудит классификации

- `make audit-vehicle-classifications` — проверить готовность к классификации
  8702–8704.
- `make backfill-vehicle-attribute-inferences` — выполнить dry-run восстановления
  признаков.

Запись результатов backfill включается явно:

```bash
make backfill-vehicle-attribute-inferences \
  BACKFILL_VEHICLE_ATTRIBUTE_INFERENCES_ARGS=--write
```

## Важное различие локального и Docker-запуска

Цели постобработки используют `.venv/bin/python`. На сервере без `.venv`
запускайте утилиту отдельным контейнером, например:

```bash
docker compose -f compose.prod.yaml run --rm api \
  python -m autohome.cli.calculate_customs_payments
```
