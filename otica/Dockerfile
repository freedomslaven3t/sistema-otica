FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 PORT=8000 ABRIR_NAVEGADOR=0

WORKDIR /app
COPY requirements.txt requirements-online.txt ./
RUN pip install --no-cache-dir -r requirements-online.txt

COPY . .
RUN useradd --create-home appuser && mkdir -p dados && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["python", "app.py"]
