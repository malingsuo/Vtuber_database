FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
