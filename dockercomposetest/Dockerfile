FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 1. Base-Requirements (perfekt gecacht)
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

# 2. Test- und Web-Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir python-multipart

# 3. Code kopieren
COPY . .

CMD ["python", "src/app.py"]