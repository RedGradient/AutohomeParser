from pathlib import Path

# Имя Scrapy-проекта, используемое во внутренних компонентах и логах.
BOT_NAME = "autohome"
# Пакеты Python, в которых Scrapy ищет существующих пауков.
SPIDER_MODULES = ["autohome.spiders"]
# Пакет, в котором команда genspider создаёт новых пауков.
NEWSPIDER_MODULE = "autohome.spiders"

# Не запрещать запросы на основании файла robots.txt сайта.
ROBOTSTXT_OBEY = False
# Не хранить и не отправлять cookies между запросами.
COOKIES_ENABLED = False
# Не запускать встроенную консоль удалённого управления Scrapy.
TELNETCONSOLE_ENABLED = False

# Максимальное общее количество одновременно выполняемых запросов.
CONCURRENT_REQUESTS = 100
# Максимальное количество одновременных запросов к одному домену.
CONCURRENT_REQUESTS_PER_DOMAIN = 24
# Минимальная задержка между запросами к одному домену в секундах.
DOWNLOAD_DELAY = 0
# Величина случайного отклонения задержки между запросами.
DOWNLOAD_DELAY_JITTER = 0
# Максимальное время ожидания ответа на один запрос в секундах.
DOWNLOAD_TIMEOUT = 30

# Автоматически регулировать скорость запросов по задержкам ответов сервера.
AUTOTHROTTLE_ENABLED = True
# Начальная задержка AutoThrottle в секундах.
AUTOTHROTTLE_START_DELAY = 0.1
# Максимальная задержка, которую может установить AutoThrottle, в секундах.
AUTOTHROTTLE_MAX_DELAY = 10
# Желаемое среднее количество параллельных запросов на один сервер.
AUTOTHROTTLE_TARGET_CONCURRENCY = 16

# Повторять запросы, завершившиеся временной ошибкой.
RETRY_ENABLED = True
# Количество повторных попыток после первого неудачного запроса.
RETRY_TIMES = 5
# HTTP-коды, при которых запрос необходимо повторить.
RETRY_HTTP_CODES = [408, 425, 429, 500, 502, 503, 504]

# HTTP-заголовки, автоматически добавляемые ко всем запросам паука.
DEFAULT_REQUEST_HEADERS = {
    # Запрашивать JSON, но разрешать серверу вернуть другой тип содержимого.
    "Accept": "application/json, text/plain, */*",
    # Предпочитать китайский язык ответа, затем английский.
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    # Представляться обычным браузером Chrome для совместимости с Autohome.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Подключить pipeline SQLAlchemy; число задаёт порядок его выполнения.
ITEM_PIPELINES = {"autohome.pipelines.SqlAlchemyPipeline": 300}
# Адрес SQLite-базы с абсолютным путём к файлу внутри каталога data.
DATABASE_URL = f"sqlite:///{Path('data/autohome.sqlite3').resolve()}"
# Количество элементов, накапливаемых перед одной пакетной записью в БД.
DATABASE_BATCH_SIZE = 1000

# Минимальный уровень сообщений, выводимых в журнал Scrapy.
LOG_LEVEL = "INFO"
# Кодировка экспортируемых Scrapy файлов, если будет включён feed export.
FEED_EXPORT_ENCODING = "utf-8"
