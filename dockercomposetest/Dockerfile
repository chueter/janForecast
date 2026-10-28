FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 1. Zuerst die schweren Base-Requirements kopieren & installieren (Wird perfekt gecacht!)
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

# 2. Danach erst die restlichen/flexiblen Requirements (z.B. mistralai)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Zu guter Letzt den eigentlichen Python-Code
COPY . .

CMD ["python", "src/app.py"]