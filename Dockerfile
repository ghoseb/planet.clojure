# Lambda container image for Planet Clojure (arm64 / Graviton).
#
# Build:  docker build -t planet .
# The AWS base image includes the Runtime Interface Emulator, so the same
# image can be invoked locally on :8080 (see compose.yaml).

FROM public.ecr.aws/lambda/python:3.13 AS build
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt \
 && uv pip install --no-cache --target /deps -r requirements.txt

FROM public.ecr.aws/lambda/python:3.13
COPY --from=build /deps ${LAMBDA_TASK_ROOT}
COPY src/planet ${LAMBDA_TASK_ROOT}/planet
COPY config.ini ${LAMBDA_TASK_ROOT}/config.ini
COPY static ${LAMBDA_TASK_ROOT}/static
CMD ["planet.handler.handler"]
