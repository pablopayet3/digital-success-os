# Digital Success OS (mini). Synthetic data, fictional company.
#
# One image serves both the app (Streamlit, port 8501) and the API (FastAPI, port 8000).
# A small demo world is built inside the image, so the hosted demo has data, runs
# offline, and holds no API key.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.12.6
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DSO_ENV=dev \
    DSO_OFFLINE_MODE=true \
    DSO_LLM_STAND_IN=true

# Dependencies first: this layer is rebuilt only when the lock file changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Generate a small world, run the pipeline, train, simulate ten days, write the reports.
RUN uv run --no-dev python run.py demo 10 --profile small

# Hosted: the app is read-only and console passwords must come from the environment.
ENV DSO_HOSTED=1
EXPOSE 8501 8000

# The default command starts the app. The API uses the same image with another command
# (see docker-compose.yml and render.yaml). $PORT is set by the host when there is one.
CMD ["sh", "-c", "uv run --no-dev streamlit run app/main.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true"]