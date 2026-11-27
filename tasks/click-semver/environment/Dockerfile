FROM python:3.12-slim
# less: click's pager tests shell out to it.
RUN apt-get update && apt-get install -y --no-install-recommends git less \
    && rm -rf /var/lib/apt/lists/*
# Fetch only the base commit so the agent cannot see later upstream history.
RUN git init -q /app/repo && cd /app/repo \
    && git fetch -q --depth 1 https://github.com/pallets/click cf19179e8e2fd54c601378cec9e0d21bb12b6fb1 \
    && git checkout -q FETCH_HEAD
WORKDIR /app/repo
RUN pip install --no-cache-dir -e . pytest==8.4.1
