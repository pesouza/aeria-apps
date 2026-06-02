FROM python:3.11-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY . .

EXPOSE 8000

CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:8000", "app:app", "--workers", "2", "--threads", "4", "--access-logfile", "-"]