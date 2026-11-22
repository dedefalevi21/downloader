FROM python:3.11-slim

WORKDIR /app

# FFmpeg wajib untuk menggabungkan video + audio YouTube
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY index.html .
COPY assets/ ./assets/

EXPOSE 8080

CMD ["python", "app.py"]
