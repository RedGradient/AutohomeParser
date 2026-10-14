SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

# Используемые по умолчанию сетевые интерфейсы.
WIFI_IF ?= wlp0s20f3
ETH_IF ?= enp0s20f0u1c4i2

# Отдельные таблицы и приоритеты выбраны из редко используемого диапазона.
WIFI_TABLE := 10101
ETH_TABLE := 10102
WIFI_PRIORITY := 10101
ETH_PRIORITY := 10102

.PHONY: help network-up network-down network-status network-test

help:
	@echo "Доступные команды:"
	@echo "  make network-up      — включить временную маршрутизацию"
	@echo "  make network-down    — удалить временные правила"
	@echo "  make network-status  — показать интерфейсы и правила"
	@echo "  make network-test    — проверить маршруты и внешние IP"
	@echo
	@echo "Интерфейсы можно переопределить:"
	@echo "  make WIFI_IF=wlan0 ETH_IF=eth0 network-up"

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
