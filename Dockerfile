FROM python:3.7-alpine
RUN apk add --update --no-cache --virtual .build-deps g++ gcc libxml2-dev libxslt-dev python3-dev && \
    apk add --no-cache libxslt && \
    pip install --no-cache-dir lxml>=3.5.0 && \
    apk del .build-deps
WORKDIR app
COPY . .
RUN pip install -r requirements.txt
ENTRYPOINT ["python","./docker_entry.py"]