# Bluffhouse, hosted: the full app (replay theater, live games with
# bring-your-own API keys, leaderboards). The frontend build is committed,
# so this image needs Python only.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# runs/ is ephemeral unless the host mounts a volume here
RUN mkdir -p /app/runs
ENV HOST=0.0.0.0 PORT=8080
EXPOSE 8080

CMD ["bluffhouse", "serve", "--dir", "/app/runs", "--no-open"]
