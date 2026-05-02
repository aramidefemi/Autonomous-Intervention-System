# Optional: run API in Compose later. Local dev: uvicorn against compose infra.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir -U pip
COPY pyproject.toml readme.md ./
COPY src ./src
# Editable install without VCS: copy tree and install non-editable
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "ais.main:app", "--host", "0.0.0.0", "--port", "8000"]
