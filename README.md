# Парсер Autohome

Scrapy-паук получает данные из JSON-эндпоинтов Autohome, нормализует их и
сохраняет в SQLite через SQLAlchemy.

Для первоначальной загрузки `treeMenu` необходима системная команда `curl`.
Этот ответ CDN Autohome не всегда корректно завершается в браузерах и загрузчике
Twisted, который использует Scrapy. Полученный ответ кешируется в
`data/tree_menu.json`; остальные запросы выполняются средствами Scrapy.

## Установка и запуск

```bash
python -m pip install -r requirements.txt
scrapy crawl cars
```

Ограниченная проверка каталога:

```bash
scrapy crawl cars -a max_series=10 -a max_config_requests_per_series=1
```

Проверка одной серии:

```bash
scrapy crawl cars -a series_id=18 -a city_id=110100
```

Быстрая проверка с двумя запросами полных конфигураций:

```bash
scrapy crawl cars -a series_id=18 -a max_config_requests_per_series=2
```

Дозагрузка отсутствующих полных конфигураций после прерванного обхода:

```bash
scrapy crawl cars -a resume_configs=1
```

Проверка режима дозагрузки максимум на 20 комплектациях:

```bash
scrapy crawl cars -a resume_configs=1 -a max_resume_specs=20
```

Режим дозагрузки не обращается к эндпоинтам каталога и списков серий. Он
выбирает поддерживающие полную конфигурацию комплектации, для которых в таблице
`spec_parameters` ещё нет записей.

База данных создаётся в `data/autohome.sqlite3`.

## Таблицы

- `brands` — бренды;
- `series` — серии автомобилей;
- `specs` — конкретные комплектации;
- `parameter_definitions` — определения технических характеристик;
- `spec_parameters` — значения характеристик комплектаций.

Поле `spec_parameters.title_id` ссылается на
`parameter_definitions.title_id`. Обозначения Autohome сохраняются без
изменений: `●` означает штатное оснащение, `○` — опцию, а `-` — отсутствие
оборудования.

## Локальный словарь

Файл `autohome/data/translations_ru.json` содержит русские переводы названий
характеристик, типовых значений и повторяющихся фрагментов названий
комплектаций. Если перевода нет, исходный китайский текст должен сохраняться
без изменений.
