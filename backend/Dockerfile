FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements/linux-runtime.lock /app/requirements/linux-runtime.lock
COPY pyproject.toml /app/pyproject.toml

RUN python -m pip install --no-cache-dir --require-hashes \
        -r requirements/linux-runtime.lock

COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation . \
    && python -m pip check

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
