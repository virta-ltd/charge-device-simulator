FROM python:3.7-alpine
WORKDIR app
COPY . .
RUN pip install -r requirements.txt
ENTRYPOINT ["python","./simulator-executor.py"]