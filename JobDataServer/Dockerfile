FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY JobDataServer/requirements.txt ./JobDataServer/requirements.txt
RUN pip install --no-cache-dir -r JobDataServer/requirements.txt

COPY JobDataServer ./JobDataServer
COPY WebScraper ./WebScraper

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/JobDataServer"]