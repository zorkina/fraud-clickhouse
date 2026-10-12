FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 1000 appuser
COPY --chown=appuser:appuser app app
COPY --chown=appuser:appuser sql sql
COPY --chown=appuser:appuser tests tests
RUN mkdir data results && chown appuser:appuser data results
USER appuser
CMD ["python", "-m", "app.run"]
