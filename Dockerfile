# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# build-essential is only present in the builder stage for packages that do not
# publish wheels for the target platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

# Optional extras can be enabled by the builder, for example:
#   docker build --build-arg INSTALL_EXTRAS=openshell -t anytype-agent:openshell .
# The default image installs only the declared production dependencies.
ARG INSTALL_EXTRAS=""
RUN python -m pip install --upgrade pip \
    && if [ -n "$INSTALL_EXTRAS" ]; then \
        python -m pip wheel --wheel-dir /wheels ".[${INSTALL_EXTRAS}]"; \
    else \
        python -m pip wheel --wheel-dir /wheels .; \
    fi

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

WORKDIR /app

COPY --from=builder /wheels /wheels

RUN python -m pip install --no-index --find-links=/wheels anytype-agent \
    && rm -rf /wheels \
    && mkdir -p /etc/guardrails /etc/openshell/policies /tmp/.cache /tmp/anytype-agent \
    && useradd --uid 10001 --gid 0 --home-dir /tmp --no-create-home --shell /usr/sbin/nologin app \
    && chown -R 10001:0 /app /etc/guardrails /etc/openshell /tmp/.cache /tmp/anytype-agent \
    && chmod -R g=u /app /etc/guardrails /etc/openshell /tmp/.cache /tmp/anytype-agent

USER 10001

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
