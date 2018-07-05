# build
FROM python:alpine AS build

RUN apk update && apk add build-base libffi-dev

WORKDIR /tmp
COPY requirements.txt /tmp/
RUN pip wheel -w wheels -r /tmp/requirements.txt gunicorn

# deploy
FROM python:alpine

COPY --from=build /tmp/wheels /tmp/wheels
RUN pip install /tmp/wheels/* && rm -r /tmp/wheels

WORKDIR /app
RUN mkdir -p app

COPY journal /app/journal
COPY run-gunicorn.sh /app/
COPY wsgi.py /app/

ENTRYPOINT ["./run-gunicorn.sh"]
CMD ["-b=0.0.0.0:8080"]

EXPOSE 8080
STOPSIGNAL SIGINT
