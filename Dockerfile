FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY configs ./configs
COPY data ./data
COPY reports ./reports

EXPOSE 4001
