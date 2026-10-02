FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 app
USER app
WORKDIR /home/app
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["fast-verify"]
CMD ["--help"]
