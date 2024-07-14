FROM python:3.12.2-bookworm

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY smartthings-ac-exporter.py ./
COPY device_metrics.json ./

CMD [ "python", "./smartthings-ac-exporter.py" ]
