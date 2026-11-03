FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY modernize43 ./modernize43

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["python3", "-m", "modernize43", "--host", "0.0.0.0", "--port", "8080"]
