FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && groupadd --system pulse && useradd --system --gid pulse pulse
COPY app app
COPY alembic alembic
COPY alembic.ini .
USER pulse
