FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl iproute2 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system autohome \
    && useradd --system --gid autohome --home-dir /app autohome

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY autohome ./autohome
COPY alembic ./alembic
COPY alembic.ini ./
COPY scrapy.cfg run_multi.py calculate_customs_payments.py ./

USER autohome

EXPOSE 8000

CMD ["uvicorn", "autohome.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
