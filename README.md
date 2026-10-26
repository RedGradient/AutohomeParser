# Autohome Parser

[![CI/CD](https://github.com/RedGradient/AutohomeParser/actions/workflows/ci-cd.yaml/badge.svg)](https://github.com/RedGradient/AutohomeParser/actions/workflows/ci-cd.yaml)
[![codecov](https://codecov.io/gh/RedGradient/AutohomeParser/graph/badge.svg)](https://codecov.io/gh/RedGradient/AutohomeParser)

> **Статус: Alpha**

## Содержание

- [Описание проекта](#описание-проекта)
- [API](#api)
- [Архитектура](#архитектура)
- [Модель данных](#модель-данных)
- [Запуск](#запуск)
- [Многопроцессный локальный запуск](#многопроцессный-локальный-запуск)
- [Документация](#документация)

## Описание проекта

Проект загружает автомобильный каталог из API и страниц Autohome и сохраняет
его в PostgreSQL. Большая часть каталога, конфигураций и рейтингов приходит как
JSON; страницы фотогалерей разбираются из HTML. Scrapy-парсер собирает
производителей, бренды, серии, комплектации, характеристики, рейтинги продаж и
ссылки на фотографии. Во время записи данные нормализуются, цены переводятся из
китайского формата в числовой, а известные названия и характеристики — в
принятые русские или международные обозначения. Исходные ответы API сохраняются
в поле `raw_json` соответствующей таблицы.

Полный каталог данных на 26 октября 2026 года занимает около **13 ГБ**. В эту
оценку входят таблицы, индексы и служебные файлы PostgreSQL.

Для комплектаций можно предварительно рассчитать ввозную пошлину, таможенный
сбор, утилизационный сбор, акциз и НДС. Расчёт использует курсы CNY и EUR Банка
России и носит оценочный характер: каталог не содержит стоимость доставки и
страхования до границы.

Celery beat ежедневно в 08:00 по Москве проверяет курсы ЦБ. При изменении курса
Celery worker пересчитывает таможенные платежи, а при неизменном курсе
досчитывает отсутствующие сценарии. Перерасчёт можно запустить вручную:

```bash
docker compose -f compose.prod.yaml run --rm api \
  python -m autohome.cli.calculate_customs_payments
```

Подробности расчётов приведены в
[`docs/customs-calculations.md`](docs/customs-calculations.md).

Проект также формирует агрегированный снимок состояния каталога и таможенных
расчётов. Готовый отчёт доступен на странице
`http://localhost:8000/metrics/customs`.

## API

FastAPI предоставляет версионированный read-only API `/api/v1`. Прикладные
эндпоинты требуют JWT; `/health`, страница и API агрегированных метрик, Swagger,
ReDoc, OpenAPI и выдача токена остаются публичными.

Основные эндпоинты:

- `/api/v1/auth/token` — получение JWT;
- `/api/v1/manufacturers`, `/api/v1/manufacturers/{id}` — список и карточка
  производителя;
- `/api/v1/brands`, `/api/v1/brands/{id}` — список и карточка бренда;
- `/api/v1/series`, `/api/v1/series/{id}` — серии, цены и официальные
  изображения;
- `/api/v1/specs`, `/api/v1/specs/{id}` — комплектации и их цены;
- `/api/v1/specs/{id}/parameters` — полная конфигурация комплектации;
- `/api/v1/modifications`, `/api/v1/modifications/{id}` — нормализованные
  технические модификации;
- `/api/v1/series/{series_id}/modifications` — модификации серии;
- `/api/v1/modifications/{id}/specs` — комплектации модификации;
- `/api/v1/series/{series_id}/photos` — фотографии и цвета;
- `/api/v1/series/{series_id}/gallery-colors` — доступные цвета галереи;
- `/api/v1/customs-calculations` — рассчитанные таможенные платежи;
- `/api/v1/specs/{spec_id}/customs-calculations` — расчёты комплектации;
- `/api/v1/metrics/customs` — последний снимок метрик каталога и расчётов.

После запуска доступны:

- Swagger UI: `http://localhost:8000/docs`;
- ReDoc: `http://localhost:8000/redoc`;
- OpenAPI JSON: `http://localhost:8000/openapi.json`;
- healthcheck: `http://localhost:8000/health`;
- отчёт по таможенным расчётам: `http://localhost:8000/metrics/customs`.

Пример получения токена:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"autohome","password":"password"}'
```

Токен передаётся как `Authorization: Bearer <token>`. Полный набор фильтров,
схем ответов и допустимых значений документируется непосредственно в Swagger.

## Архитектура

Парсер и HTTP API — независимые приложения. Они не вызывают друг друга: парсер
записывает данные в PostgreSQL, а API читает их оттуда.

```text
Autohome ──> Scrapy parser ──> PostgreSQL <── FastAPI <── nginx
                                  ^
                                  │
ЦБ РФ ──> Celery beat ──> Redis ──> Celery worker
```

- **Scrapy** загружает и нормализует каталог;
- **FastAPI** предоставляет API;
- **PostgreSQL** хранит каталог и актуальные расчёты;
- **Alembic** управляет схемой БД;
- **Celery beat/worker** периодически обновляют курсы и расчёты;
- **Redis** служит брокером Celery;
- **nginx** публикует API в production.

Сбой или остановка API не останавливает парсер. Аналогично парсер не требуется
для чтения уже загруженного каталога через API.

## Модель данных

Главная иерархия каталога:

```text
Manufacturer ── Brand ── Series ── Spec
                              └── Modification
```

- `manufacturers` — производители и заводы;
- `brands` — автомобильные бренды;
- `series` — модельные серии;
- `specs` — конкретные комплектации;
- `spec_parameters` — отдельные значения характеристик комплектаций;
- `modifications` — технически одинаковые варианты комплектаций;
- `series_photos` — прямые ссылки на фотографии серий;
- `customs_calculations` — актуальные сценарии таможенного расчёта;
- `customs_payment_results` — отдельные виды платежей сценария.
- `customs_metrics` — последний агрегированный снимок состояния расчётов.

`modifications` не приходит из Autohome как готовая сущность. Проект формирует
таблицу самостоятельно, объединяя комплектации одной серии и модельного года с
одинаковым набором нормализованных характеристик: силовой установкой, приводом,
трансмиссией и кузовом. Если части этих характеристик не хватает, комплектация
остаётся без `modification_id`, чтобы её случайно не объединить с технически
другим автомобилем.

Полный перечень таблиц, назначение и связи описаны в
[`docs/database-schema.md`](docs/database-schema.md).

## Запуск

Требования для Docker-запуска: Git, Docker Engine с Compose plugin и Linux.
Для локального Python-запуска нужен Python 3.13.

Скопируйте настройки и замените демонстрационные значения:

```bash
cp .env.example .env
```

Запуск проекта для локальной разработки:

```bash
docker compose -f compose.dev.yaml up -d --build --wait
```

API будет доступен на `http://127.0.0.1:8000`. Команда запускает PostgreSQL,
применяет миграции Alembic, затем поднимает API, Redis и Celery.

Production-конфигурация:

```bash
docker compose -f compose.prod.yaml up -d --build --wait
```

Однопроцессный запуск паука из Python-окружения:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl cars
```

Режим дозагрузки отсутствующих конфигураций:

```bash
.venv/bin/scrapy crawl cars -a resume_configs=1
```

Все параметры паука и примеры приведены в
[`docs/scrapy.md`](docs/scrapy.md), команды проекта — в
[`docs/makefile.md`](docs/makefile.md).

## Документация

- [Полная схема данных](docs/database-schema.md)
- [Команды Makefile](docs/makefile.md)
- [Scrapy и режимы загрузки](docs/scrapy.md)
- [Таможенные расчёты](docs/customs-calculations.md)
- [Метрики таможенных расчётов](docs/customs-metrics.md)
- [Production deployment](docs/deployment.md)
- [Переводы и нормализация](docs/translations.md)
