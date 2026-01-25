FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && npm --version \
  && rm -rf /var/lib/apt/lists/*

COPY src/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONPATH=/app/src/python_module:/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "orchestrator.main", "--force"]
