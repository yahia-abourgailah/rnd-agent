FROM python:3.11-slim AS base

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY alembic.ini ./
COPY scripts ./scripts
COPY evals ./evals


# The API serves reads and the chatbot; it never fetches a page, so it does not
# carry the browser. Keeping it out builds this image in seconds rather than
# minutes.
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Collection does need a browser: Nawy's new-launches page is JS-rendered.
FROM base AS worker
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium
CMD ["python", "-m", "pipeline.flows"]
