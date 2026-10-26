from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LOG_COLORS = (
    "\033[96m",  # Ярко-голубой.
    "\033[95m",  # Ярко-пурпурный.
    "\033[93m",  # Ярко-жёлтый.
    "\033[92m",  # Ярко-зелёный.
    "\033[94m",  # Ярко-синий.
    "\033[91m",  # Ярко-красный.
)
LOG_COLOR_RESET = "\033[0m"
AUTOHOME_HOSTS = (
    "www.autohome.com.cn",
    "car.app.autohome.com.cn",
    "car.autohome.com.cn",
)
TREE_URL = "https://www.autohome.com.cn/web-main/car/web/price/treeMenu?extendseries=1"


def parse_arguments() -> argparse.Namespace:
    """Разобрать параметры многопроцессного запуска."""
    parser = argparse.ArgumentParser(
        description="Запуск отдельного процесса Scrapy для каждого интерфейса."
    )
    parser.add_argument(
        "--interfaces",
        required=True,
        help="Имена интерфейсов через запятую, например wlp0s20f3,enp0s20f0u1c4i2.",
    )
    parser.add_argument("--city-id", default="110100", help="Идентификатор города.")
    parser.add_argument(
        "--max-series",
        type=int,
        default=0,
        help="Максимум серий на один worker; 0 означает без ограничения.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Общая база workers; по умолчанию берётся из DATABASE_URL.",
    )
    parser.add_argument(
        "--resume-configs",
        action="store_true",
        help="Дозагрузить только отсутствующие полные конфигурации из общей БД.",
    )
    parser.add_argument(
        "--max-resume-specs",
        type=int,
        default=0,
        help="Максимум недостающих комплектаций на worker в режиме дозагрузки.",
    )
    parser.add_argument(
        "--sales-months",
        type=int,
        default=6,
        help="Количество последних доступных месяцев рейтингов продаж.",
    )
    parser.add_argument(
        "--skip-sales",
        action="store_true",
        help="Не загружать месячные рейтинги серий и марок.",
    )
    parser.add_argument(
        "--skip-galleries",
        action="store_true",
        help="Не загружать фотогалереи серий.",
    )
    parser.add_argument(
        "--gallery-categories",
        default="1,10,3,12,53,51",
        help="Идентификаторы категорий галереи через запятую.",
    )
    parser.add_argument(
        "--skip-route-check",
        action="store_true",
        help="Не проверять, что маршрут исходного IP проходит через его интерфейс.",
    )
    parser.add_argument(
        "--skip-dns-check",
        action="store_true",
        help="Не проверять доступность DNS-адресов Autohome перед запуском.",
    )
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=60.0,
        help="Ожидание штатного завершения workers после Ctrl+C в секундах.",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=Path("data/tree_menu.json"),
        help="Общий файл дерева каталога, подготовленный мастер-процессом.",
    )
    parser.add_argument(
        "--skip-customs-recalculation",
        action="store_true",
        help="Не досчитывать отсутствующие таможенные платежи после парсинга.",
    )
    return parser.parse_args()


def interface_ipv4(interface: str) -> str:
    """Получить первый глобальный IPv4-адрес сетевого интерфейса."""
    completed = subprocess.run(
        ["ip", "-j", "-4", "addr", "show", "dev", interface],
        check=True,
        capture_output=True,
        text=True,
    )
    records = json.loads(completed.stdout)
    for record in records:
        for address in record.get("addr_info", []):
            if address.get("family") == "inet" and address.get("scope") == "global":
                return str(address["local"])
    raise RuntimeError(f"На интерфейсе {interface} нет глобального IPv4-адреса")


def routed_interface(source_ip: str) -> str:
    """Определить интерфейс маршрута в интернет для исходного IP."""
    completed = subprocess.run(
        ["ip", "-j", "-4", "route", "get", "1.1.1.1", "from", source_ip],
        check=True,
        capture_output=True,
        text=True,
    )
    routes = json.loads(completed.stdout)
    if not routes or not routes[0].get("dev"):
        raise RuntimeError(f"Не найден маршрут для исходного адреса {source_ip}")
    return str(routes[0]["dev"])


def resolve_ipv4(hostname: str) -> list[str]:
    """Получить уникальные IPv4-адреса домена в порядке ответа DNS."""
    records = socket.getaddrinfo(
        hostname,
        443,
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )
    addresses: list[str] = []
    for record in records:
        address = str(record[4][0])
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise RuntimeError(f"DNS не вернул IPv4-адреса для {hostname}")
    return addresses


def can_connect(source_ip: str, target_ip: str, timeout: float = 3.0) -> bool:
    """Проверить TCP-подключение к HTTPS с указанного исходного IP."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(timeout)
    try:
        connection.bind((source_ip, 0))
        connection.connect((target_ip, 443))
    except OSError:
        return False
    finally:
        connection.close()
    return True


def check_autohome_dns(interface: str, source_ip: str) -> None:
    """Убедиться, что каждый домен Autohome имеет доступный CDN-адрес."""
    for hostname in AUTOHOME_HOSTS:
        addresses = resolve_ipv4(hostname)
        with ThreadPoolExecutor(max_workers=min(16, len(addresses))) as executor:
            checks = executor.map(
                lambda address: can_connect(source_ip, address),
                addresses,
            )
            available = [
                address
                for address, is_available in zip(addresses, checks)
                if is_available
            ]
        unavailable = [address for address in addresses if address not in available]
        if not available:
            raise RuntimeError(
                f"{interface}: ни один адрес {hostname} недоступен с {source_ip}; "
                f"DNS вернул {', '.join(addresses)}"
            )
        print(
            f"Проверка DNS {interface}: {hostname} — доступны {', '.join(available)}",
            flush=True,
        )
        if unavailable:
            print(
                f"Предупреждение: {hostname} также вернул недоступные адреса "
                f"{', '.join(unavailable)}; DNS-кеш Scrapy будет отключён.",
                file=sys.stderr,
                flush=True,
            )


def require_database_url(configured_url: str | None) -> str:
    """Вернуть общий URL базы или завершить запуск с понятной ошибкой."""
    if not configured_url:
        raise SystemExit("Не задан DATABASE_URL или --database-url")
    return configured_url


def database_display_name(database_url: str) -> str:
    """Вернуть безопасное представление URL базы без пароля."""
    from sqlalchemy.engine import make_url

    return make_url(database_url).render_as_string(hide_password=True)


def validate_database(database_url: str) -> None:
    """Проверить подключение и актуальность миграций базы."""
    from autohome.database_migrations import require_current_database

    require_current_database(database_url)


def download_catalog(
    catalog_path: Path,
    source_addresses: list[str],
    force_refresh: bool,
) -> None:
    """Один раз получить каталог и атомарно сохранить его до запуска workers."""
    catalog_path = catalog_path.resolve()
    if (
        not force_refresh
        and catalog_path.exists()
        and catalog_path.stat().st_size > 100_000
    ):
        print(f"Мастер использует кеш каталога {catalog_path}", flush=True)
        return

    errors: list[str] = []
    for source_address in source_addresses:
        temporary_path = catalog_path.with_name(
            f".{catalog_path.name}.{os.getpid()}.tmp"
        )
        command = [
            "curl",
            "-fsS",
            "--compressed",
            "--connect-timeout",
            "15",
            "--max-time",
            "300",
            "--retry",
            "3",
            "--retry-all-errors",
            "--interface",
            source_address,
            "-H",
            "Accept: application/json, text/plain, */*",
            "-H",
            "Referer: https://www.autohome.com.cn/price",
            TREE_URL,
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=930,
            )
            body = completed.stdout
            if len(body) <= 100_000:
                raise RuntimeError(f"слишком короткий ответ: {len(body)} байт")
            json.loads(body)
            catalog_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_bytes(body)
            os.replace(temporary_path, catalog_path)
            print(
                f"Мастер сохранил каталог: {len(body)} байт, "
                f"источник={source_address}, файл={catalog_path}",
                flush=True,
            )
            return
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            temporary_path.unlink(missing_ok=True)
            errors.append(f"{source_address}: {error}")

    raise RuntimeError("; ".join(errors) or "нет доступных исходных адресов")


def worker_color(worker_index: int) -> str:
    """Выбрать постоянный цвет консольного журнала worker-процесса."""
    return LOG_COLORS[worker_index % len(LOG_COLORS)]


def run_worker(
    worker_index: int,
    worker_count: int,
    interface: str,
    bind_address: str,
    database_url: str,
    city_id: str,
    max_series: int,
    resume_configs: bool,
    max_resume_specs: int,
    sales_months: int,
    skip_sales: bool,
    skip_galleries: bool,
    gallery_categories: str,
    catalog_path: str,
) -> None:
    """Запустить Scrapy в изолированном дочернем процессе."""
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    from autohome.spiders.cars import CarsSpider

    settings = get_project_settings()
    color = worker_color(worker_index)
    settings.set("DATABASE_URL", database_url, priority="cmdline")
    settings.set("BOT_NAME", f"autohome-{interface}", priority="cmdline")
    settings.set("DNSCACHE_ENABLED", False, priority="cmdline")
    settings.set(
        "LOG_FORMAT",
        (
            f"{color}[{interface}] "
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
            f"{LOG_COLOR_RESET}"
        ),
        priority="cmdline",
    )
    crawler = CrawlerProcess(settings)
    crawler.crawl(
        CarsSpider,
        city_id=city_id,
        max_series=str(max_series),
        worker_index=str(worker_index),
        worker_count=str(worker_count),
        bind_address=bind_address,
        resume_configs="1" if resume_configs else "0",
        max_resume_specs=str(max_resume_specs),
        sales_months=str(sales_months),
        parse_sales="0" if skip_sales else "1",
        parse_galleries="0" if skip_galleries else "1",
        gallery_categories=gallery_categories,
        catalog_path=catalog_path,
        catalog_preloaded="1",
    )
    crawler.start()


def terminate_workers(processes: list[multiprocessing.Process]) -> None:
    """Принудительно завершить живые worker-процессы и дождаться их остановки."""
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        process.join()


def wait_for_graceful_shutdown(
    processes: list[multiprocessing.Process], timeout: float
) -> bool:
    """Дождаться штатного завершения workers в пределах заданного времени."""
    deadline = time.monotonic() + max(0.0, timeout)
    while any(process.is_alive() for process in processes):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        for process in processes:
            if process.is_alive():
                process.join(timeout=min(0.25, remaining))
    return True


def run_stale_customs_recalculation(database_url: str) -> None:
    """Досчитать отсутствующие или изменившиеся таможенные платежи."""
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [
            sys.executable,
            "-m",
            "autohome.cli.calculate_customs_payments",
            "--mode",
            "stale",
        ],
        check=True,
        env=environment,
    )


def main() -> int:
    """Проверить интерфейсы, запустить worker-процессы и дождаться завершения."""
    args = parse_arguments()
    interfaces = [item.strip() for item in args.interfaces.split(",") if item.strip()]
    if not interfaces:
        raise SystemExit("Не указан ни один сетевой интерфейс")
    if len(set(interfaces)) != len(interfaces):
        raise SystemExit("Имена сетевых интерфейсов не должны повторяться")

    database_url = require_database_url(args.database_url)
    workers: list[tuple[str, str]] = []
    for interface in interfaces:
        address = interface_ipv4(interface)
        if not args.skip_route_check:
            actual_interface = routed_interface(address)
            if actual_interface != interface:
                raise SystemExit(
                    f"Адрес {address} маршрутизируется через {actual_interface}, а не "
                    f"через {interface}. Сначала выполните make network-up."
                )
        if not args.skip_dns_check:
            try:
                check_autohome_dns(interface, address)
            except (OSError, RuntimeError) as error:
                raise SystemExit(
                    f"Проверка DNS завершилась ошибкой: {error}"
                ) from error
        workers.append((interface, address))

    try:
        validate_database(database_url)
    except Exception as error:
        safe_url = database_display_name(database_url)
        raise SystemExit(f"База {safe_url} не готова к запуску: {error}") from error

    catalog_path = args.catalog_path.resolve()
    try:
        download_catalog(
            catalog_path,
            [address for _, address in workers],
            force_refresh=args.resume_configs,
        )
    except Exception as error:
        raise SystemExit(f"Не удалось подготовить дерево каталога: {error}") from error

    context = multiprocessing.get_context("spawn")
    processes: list[multiprocessing.Process] = []
    safe_database_url = database_display_name(database_url)
    for index, (interface, address) in enumerate(workers):
        color = worker_color(index)
        print(
            f"{color}Worker {index}: интерфейс={interface}, IP={address}, "
            f"БД={safe_database_url}{LOG_COLOR_RESET}",
            flush=True,
        )
        process = context.Process(
            name=f"scrapy-{interface}",
            target=run_worker,
            args=(
                index,
                len(workers),
                interface,
                address,
                database_url,
                args.city_id,
                args.max_series,
                args.resume_configs,
                args.max_resume_specs,
                args.sales_months,
                args.skip_sales,
                args.skip_galleries,
                args.gallery_categories,
                str(catalog_path),
            ),
        )
        process.start()
        processes.append(process)

    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        print(
            "Получен Ctrl+C. Ожидаем штатного завершения Scrapy и записи "
            f"буферов до {args.shutdown_timeout:g} секунд. Повторный Ctrl+C "
            "завершит процессы немедленно.",
            file=sys.stderr,
            flush=True,
        )
        try:
            stopped = wait_for_graceful_shutdown(processes, args.shutdown_timeout)
        except KeyboardInterrupt:
            print(
                "Получен повторный Ctrl+C; принудительно завершаем workers.",
                file=sys.stderr,
                flush=True,
            )
            terminate_workers(processes)
            return 130
        if not stopped:
            print(
                "Истёк таймаут штатного завершения; принудительно завершаем workers.",
                file=sys.stderr,
                flush=True,
            )
            terminate_workers(processes)
        else:
            print(
                "Все worker-процессы завершились штатно.",
                file=sys.stderr,
                flush=True,
            )
        return 130

    failed = [process for process in processes if process.exitcode != 0]
    if failed:
        for process in failed:
            print(
                f"Процесс {process.name} завершился с кодом {process.exitcode}",
                file=sys.stderr,
            )
        return 1
    if not args.skip_customs_recalculation:
        try:
            run_stale_customs_recalculation(database_url)
        except subprocess.CalledProcessError as error:
            print(
                f"Не удалось досчитать таможенные платежи в {safe_database_url}: "
                f"код {error.returncode}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
