FROM python:alpine3.11
COPY src/ /
RUN apk update && \
    apk add --no-cache gcc musl-dev mariadb-dev && \
    pip install --no-cache-dir -r /bot/requirements.txt && \
    apk del gcc musl-dev && \
    rm -rf /var/cache/apk/*
ENV BOT_TOKEN ""
ENV DB_USER ""
ENV DB_PASSWORD ""
ENV DB_HOST ""
ENV DB_PORT ""
ENV DB_DATABASE ""
ENV EXTENTIONS ""
CMD ["python", "/bot/bot.py"]