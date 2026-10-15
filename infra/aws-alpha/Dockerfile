FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN python -m pip install --no-cache-dir "/app[audio,aws-alpha]"

ENV SAURUS_ENV=alpha
ENV SAURUS_REGISTRY_HOST=0.0.0.0
ENV SAURUS_REGISTRY_PORT=8080

EXPOSE 8080
CMD ["python", "-m", "saurus_registry.container"]
