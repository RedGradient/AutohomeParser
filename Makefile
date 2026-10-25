SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

-include .env

COMPOSE_FILE ?= compose.dev.yaml
POSTGRES_DB ?= autohome
POSTGRES_USER ?= autohome
POSTGRES_PASSWORD ?= autohome
POSTGRES_PORT ?= 5432
AUTOHOME_INTERFACES ?= wlp0s20f3,enp0s20f0u1c4i2
DATABASE_BATCH_SIZE ?= 1000
SHUTDOWN_TIMEOUT ?= 120
NORMALIZE_VEHICLE_ATTRIBUTES_ARGS ?=
AUDIT_VEHICLE_CLASSIFICATIONS_ARGS ?=
AUDIT_INDIRECT_VEHICLE_ATTRIBUTES_ARGS ?=
AUDIT_RECYCLING_FEE_COMMERCIAL_CATEGORIES_ARGS ?=
BACKFILL_VEHICLE_ATTRIBUTE_INFERENCES_ARGS ?=
CALCULATE_IMPORT_DUTIES_ARGS ?=
API_HOST ?= 0.0.0.0
API_PORT ?= 8000
API_USERNAME ?= autohome
API_PASSWORD ?= autohome
API_JWT_SECRET ?= development-only-autohome-jwt-secret-change-me
API_JWT_TTL_SECONDS ?= 3600
DATABASE_URL ?= postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@127.0.0.1:$(POSTGRES_PORT)/$(POSTGRES_DB)

# Используемые по умолчанию сетевые интерфейсы.
WIFI_IF ?= wlp0s20f3
ETH_IF ?= enp0s20f0u1c4i2

# Отдельные таблицы и приоритеты выбраны из редко используемого диапазона.
WIFI_TABLE := 10101
ETH_TABLE := 10102
WIFI_PRIORITY := 10101
ETH_PRIORITY := 10102

.PHONY: help lint lint-fix pre-commit-install network-up network-down network-status network-test postgres-up database-migrate api-up api-logs celery-logs parser-run parser-resume parser-logs api-run database-reset parameters-reset build-modifications normalize-vehicle-attributes audit-vehicle-classifications audit-indirect-vehicle-attributes audit-recycling-fee-commercial-categories backfill-vehicle-attribute-inferences translate-db calculate-import-duties docker-down

help:
	@echo "Доступные команды:"
	@echo "  make lint            — проверить Python-код с помощью Ruff"
	@echo "  make lint-fix        — исправить и отформатировать Python-код"
	@echo "  make pre-commit-install — установить проверку Ruff перед коммитом"
	@echo "  make network-up      — включить временную маршрутизацию"
	@echo "  make network-down    — удалить временные правила"
	@echo "  make network-status  — показать интерфейсы и правила"
	@echo "  make network-test    — проверить маршруты и внешние IP"
	@echo "  make postgres-up     — запустить PostgreSQL"
	@echo "  make database-migrate — применить миграции Alembic"
	@echo "  make api-up          — собрать и запустить API с PostgreSQL в Docker"
	@echo "  make api-logs        — показать логи контейнера API"
	@echo "  make celery-logs     — показать логи worker и beat"
	@echo "  make parser-run      — запустить парсер в Docker"
	@echo "  make parser-resume   — запустить дозагрузку в Docker"
	@echo "  make api-run         — запустить FastAPI и Swagger UI"
	@echo "  make database-reset  — удалить всю БД и создать актуальные таблицы"
	@echo "  make parameters-reset — пересоздать только таблицы характеристик"
	@echo "  make build-modifications — нормализовать параметры и собрать модификации"
	@echo "  make normalize-vehicle-attributes — нормализовать кузовные характеристики"
	@echo "  make audit-vehicle-classifications — проверить классификацию 8702–8704"
	@echo "  make audit-indirect-vehicle-attributes — проверить косвенные признаки без записи"
	@echo "  make audit-recycling-fee-commercial-categories — проверить готовность M2/M3/N1/N2/N3"
	@echo "  make backfill-vehicle-attribute-inferences — dry-run косвенных признаков"
	@echo "  make translate-db    — перевести уже сохранённые данные"
	@echo "  make calculate-import-duties — рассчитать ввозную пошлину"
	@echo "  make docker-down     — остановить контейнеры"
	@echo
	@echo "Интерфейсы можно переопределить:"
	@echo "  make WIFI_IF=wlan0 ETH_IF=eth0 network-up"

lint:
	@.venv/bin/ruff check .
	.venv/bin/ruff format --check .

lint-fix:
	@.venv/bin/ruff format .
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

pre-commit-install:
	@.venv/bin/pre-commit install

network-up:
	@wifi_cidr="$$(ip -o -4 addr show dev "$(WIFI_IF)" scope global | awk 'NR == 1 {print $$4}')"
	eth_cidr="$$(ip -o -4 addr show dev "$(ETH_IF)" scope global | awk 'NR == 1 {print $$4}')"
	[[ -n "$$wifi_cidr" ]] || { echo "Нет IPv4-адреса на $(WIFI_IF)" >&2; exit 1; }
	[[ -n "$$eth_cidr" ]] || { echo "Нет IPv4-адреса на $(ETH_IF)" >&2; exit 1; }
	wifi_ip="$${wifi_cidr%/*}"
	eth_ip="$${eth_cidr%/*}"
	wifi_gateway="$$(ip -4 route show default dev "$(WIFI_IF)" | awk 'NR == 1 {print $$3}')"
	eth_gateway="$$(ip -4 route show default dev "$(ETH_IF)" | awk 'NR == 1 {print $$3}')"
	wifi_network="$$(ip -4 route show dev "$(WIFI_IF)" scope link | awk -v src="$$wifi_ip" '$$0 ~ ("src " src) {print $$1; exit}')"
	eth_network="$$(ip -4 route show dev "$(ETH_IF)" scope link | awk -v src="$$eth_ip" '$$0 ~ ("src " src) {print $$1; exit}')"
	[[ -n "$$wifi_gateway" && -n "$$wifi_network" ]] || { echo "Не найден маршрут Wi-Fi" >&2; exit 1; }
	[[ -n "$$eth_gateway" && -n "$$eth_network" ]] || { echo "Не найден маршрут Ethernet" >&2; exit 1; }
	sudo ip rule del priority $(WIFI_PRIORITY) 2>/dev/null || true
	sudo ip rule del priority $(ETH_PRIORITY) 2>/dev/null || true
	sudo ip route flush table $(WIFI_TABLE) 2>/dev/null || true
	sudo ip route flush table $(ETH_TABLE) 2>/dev/null || true
	sudo ip route add "$$wifi_network" dev "$(WIFI_IF)" src "$$wifi_ip" table $(WIFI_TABLE)
	sudo ip route add default via "$$wifi_gateway" dev "$(WIFI_IF)" table $(WIFI_TABLE)
	sudo ip rule add priority $(WIFI_PRIORITY) from "$$wifi_ip/32" lookup $(WIFI_TABLE)
	sudo ip route add "$$eth_network" dev "$(ETH_IF)" src "$$eth_ip" table $(ETH_TABLE)
	sudo ip route add default via "$$eth_gateway" dev "$(ETH_IF)" table $(ETH_TABLE)
	sudo ip rule add priority $(ETH_PRIORITY) from "$$eth_ip/32" lookup $(ETH_TABLE)
	echo "Временная маршрутизация включена:"
	echo "  $(WIFI_IF): $$wifi_ip → $$wifi_gateway"
	echo "  $(ETH_IF): $$eth_ip → $$eth_gateway"

network-down:
	@sudo ip rule del priority $(WIFI_PRIORITY) 2>/dev/null || true
	sudo ip rule del priority $(ETH_PRIORITY) 2>/dev/null || true
	sudo ip route flush table $(WIFI_TABLE) 2>/dev/null || true
	sudo ip route flush table $(ETH_TABLE) 2>/dev/null || true
	echo "Временные правила маршрутизации удалены."

network-status:
	@ip -br -4 addr show dev "$(WIFI_IF)"
	ip -br -4 addr show dev "$(ETH_IF)"
	echo
	echo "Правила проекта:"
	ip -4 rule show | grep -E '(^|:)[[:space:]]*($(WIFI_PRIORITY)|$(ETH_PRIORITY)):' || true
	echo
	echo "Таблица Wi-Fi ($(WIFI_TABLE)):"
	ip -4 route show table $(WIFI_TABLE)
	echo "Таблица Ethernet ($(ETH_TABLE)):"
	ip -4 route show table $(ETH_TABLE)

network-test:
	@wifi_ip="$$(ip -o -4 addr show dev "$(WIFI_IF)" scope global | awk 'NR == 1 {sub(/\/.*/, "", $$4); print $$4}')"
	eth_ip="$$(ip -o -4 addr show dev "$(ETH_IF)" scope global | awk 'NR == 1 {sub(/\/.*/, "", $$4); print $$4}')"
	[[ -n "$$wifi_ip" && -n "$$eth_ip" ]] || { echo "Не найдены IPv4-адреса интерфейсов" >&2; exit 1; }
	echo "Маршрут Wi-Fi:"
	ip -4 route get 1.1.1.1 from "$$wifi_ip"
	echo "Внешний IP Wi-Fi:"
	curl -4 --interface "$$wifi_ip" --connect-timeout 10 --max-time 20 -fsS https://api.ipify.org
	echo
	echo "Маршрут Ethernet:"
	ip -4 route get 1.1.1.1 from "$$eth_ip"
	echo "Внешний IP Ethernet:"
	curl -4 --interface "$$eth_ip" --connect-timeout 10 --max-time 20 -fsS https://api.ipify.org
	echo

postgres-up:
	@docker compose -f '$(COMPOSE_FILE)' up -d --wait postgres

database-migrate: postgres-up
	@docker compose -f '$(COMPOSE_FILE)' run --rm --build migrate

api-up:
	@docker compose -f '$(COMPOSE_FILE)' up -d --build --wait

api-logs:
	@docker compose -f '$(COMPOSE_FILE)' logs -f api

celery-logs:
	@docker compose -f '$(COMPOSE_FILE)' logs -f celery-worker celery-beat

parser-run: postgres-up
	@docker compose -f '$(COMPOSE_FILE)' run --rm parser \
		--interfaces '$(AUTOHOME_INTERFACES)' \
		--shutdown-timeout '$(SHUTDOWN_TIMEOUT)'

parser-resume: postgres-up
	@docker compose -f '$(COMPOSE_FILE)' run --rm parser \
		--interfaces '$(AUTOHOME_INTERFACES)' \
		--shutdown-timeout '$(SHUTDOWN_TIMEOUT)' \
		--resume-configs

api-run: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		API_USERNAME='$(API_USERNAME)' API_PASSWORD='$(API_PASSWORD)' \
		API_JWT_SECRET='$(API_JWT_SECRET)' API_JWT_TTL_SECONDS='$(API_JWT_TTL_SECONDS)' \
		.venv/bin/uvicorn autohome.api.app:create_app --factory \
		--host '$(API_HOST)' --port '$(API_PORT)'

database-reset: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python reset_database.py --yes

parameters-reset: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python reset_parameters.py --yes

build-modifications: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python build_modifications.py

normalize-vehicle-attributes: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python normalize_vehicle_attributes.py \
		$(NORMALIZE_VEHICLE_ATTRIBUTES_ARGS)

audit-vehicle-classifications: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python audit_vehicle_classifications.py \
		$(AUDIT_VEHICLE_CLASSIFICATIONS_ARGS)

audit-indirect-vehicle-attributes: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python audit_indirect_vehicle_attributes.py \
		$(AUDIT_INDIRECT_VEHICLE_ATTRIBUTES_ARGS)

audit-recycling-fee-commercial-categories: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python audit_recycling_fee_commercial_categories.py \
		$(AUDIT_RECYCLING_FEE_COMMERCIAL_CATEGORIES_ARGS)

backfill-vehicle-attribute-inferences: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python backfill_vehicle_attribute_inferences.py \
		$(BACKFILL_VEHICLE_ATTRIBUTE_INFERENCES_ARGS)

translate-db: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python translate_database.py

calculate-import-duties: postgres-up
	@DATABASE_URL='$(DATABASE_URL)' \
		.venv/bin/python calculate_import_duties.py \
		$(CALCULATE_IMPORT_DUTIES_ARGS)

docker-down:
	@docker compose -f '$(COMPOSE_FILE)' down
