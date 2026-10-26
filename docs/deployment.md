# Production deployment

Production использует `compose.prod.yaml`: PostgreSQL, миграции Alembic, API,
nginx, Redis, Celery worker и Celery beat. Парсер имеет отдельный Compose profile
и не запускается при обычном deployment.

## Подготовка сервера

Клонируйте проект под отдельным пользователем, входящим в группу `docker`:

```bash
git clone https://github.com/RedGradient/AutohomeParser.git \
  /home/deploy/autohome-parser
cd /home/deploy/autohome-parser
cp .env.example .env
```

Замените пароли, JWT secret и остальные production-значения. `.env` хранится
только на сервере и не добавляется в Git.

Первый запуск:

```bash
docker compose -f compose.prod.yaml up -d --build --wait
```

## Ручное обновление

```bash
git pull --ff-only origin master
docker compose -f compose.prod.yaml up \
  -d --build --wait --wait-timeout 1800 --remove-orphans
```

Перед API выполняется `alembic upgrade head`. Массовые миграции могут требовать
значительного свободного места для WAL и временных файлов PostgreSQL.

## Сохранность данных

База находится в именованном Docker volume `postgres_data`. Обычный
`docker compose down` его сохраняет. Команда `docker compose down -v` удаляет
данные необратимо.

При переносе каталога проекта сохраните имя Compose-проекта или явно задайте
`COMPOSE_PROJECT_NAME`, иначе Docker создаст новый пустой volume.

## Диагностика

```bash
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs --tail=100 migrate
docker compose -f compose.prod.yaml logs -f api
docker compose -f compose.prod.yaml logs -f celery-worker celery-beat
df -h /
docker system df
```

Перед крупной миграцией проверяйте свободное место и делайте `pg_dump` либо
snapshot диска.
