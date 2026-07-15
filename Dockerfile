FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir -e .

# Playwright browser binaries — only needed once JS-rendered sources are crawled.
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium

COPY . .

CMD ["python", "-m", "launch_intel.pipeline.flows"]
