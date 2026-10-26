# Scrapy и режимы загрузки

Паук `cars` загружает каталог, конфигурации, рейтинги и галереи. Настройки
передаются через `-a name=value`.

## Основные команды

Полный однопроцессный обход:

```bash
.venv/bin/scrapy crawl cars
```

Одна серия:

```bash
.venv/bin/scrapy crawl cars -a series_id=18
```

Ограниченная проверка:

```bash
.venv/bin/scrapy crawl cars \
  -a max_series=10 \
  -a max_config_requests_per_series=2
```

Без рейтингов и галерей:

```bash
.venv/bin/scrapy crawl cars \
  -a parse_sales=0 \
  -a parse_galleries=0
```

## Параметры паука

- `city_id` — город для цен, по умолчанию `110100`.
- `series_id` — загрузить только одну серию.
- `max_series` — ограничить количество серий.
- `max_config_requests_per_series` — ограничить полные конфигурации серии.
- `resume_configs` — перейти в режим дозагрузки.
- `max_resume_specs` — ограничить дозагрузку конфигураций.
- `parse_sales` — включить рейтинги и продажи, по умолчанию `1`.
- `sales_months` — число последних месяцев, по умолчанию `6`.
- `parse_galleries` — включить галереи, по умолчанию `1`.
- `gallery_categories` — категории через запятую; по умолчанию
  `1,10,3,12,53,51`.
- `worker_index` / `worker_count` — шард многопроцессного обхода.
- `bind_address` — исходный IPv4 процесса.
- `catalog_path` — путь к кешу `tree_menu.json`.
- `catalog_preloaded` — каталог уже подготовлен мастер-процессом.

## Дозагрузка

```bash
.venv/bin/scrapy crawl cars -a resume_configs=1
```

Режим использует таблицы состояния `config_crawl_tasks` и
`gallery_crawl_tasks`, а также фактически сохранённые данные. Завершённые задачи
не скачиваются повторно; отсутствующие, неуспешные и неполные ставятся в очередь.

Ограниченная ручная проверка:

```bash
.venv/bin/scrapy crawl cars \
  -a resume_configs=1 \
  -a max_resume_specs=20
```

## Каталог

Мастер загружает `treeMenu` через системный `curl`, потому что отдельные CDN
Autohome некорректно завершают ответ в Twisted. Валидный JSON сохраняется в
`data/tree_menu.json`. В многопроцессном режиме файл создаётся один раз до
старта workers.

## Многопроцессный запуск

```bash
.venv/bin/python -m autohome.cli.run_multi \
  --interfaces wlp0s20f3,enp0s20f0u1c4i2
```

Основные аргументы `autohome.cli.run_multi`:

- `--interfaces` — обязательный список интерфейсов;
- `--database-url` — общая PostgreSQL, обычно из `DATABASE_URL`;
- `--city-id`, `--max-series` — ограничения обхода;
- `--resume-configs`, `--max-resume-specs` — дозагрузка;
- `--sales-months`, `--skip-sales` — рейтинги;
- `--skip-galleries`, `--gallery-categories` — галереи;
- `--skip-route-check`, `--skip-dns-check` — диагностические отключения;
- `--shutdown-timeout` — ожидание штатной остановки;
- `--catalog-path` — общий кеш каталога;
- `--skip-customs-recalculation` — не запускать инкрементальный расчёт после
  успешного обхода.

Рейтинги загружает worker 0. Серии, конфигурации и галереи распределяются между
workers детерминированно. Логи каждого интерфейса имеют отдельный цвет.

Для нескольких физических сетей сначала настройте временную маршрутизацию:

```bash
make network-up
make network-test
make parser-run
```

После работы:

```bash
make network-down
```

Первый `Ctrl+C` ожидает штатного завершения Scrapy и записи буферов, повторный
останавливает workers принудительно.
