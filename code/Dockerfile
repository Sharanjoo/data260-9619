FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY code/main.py .
COPY code/auth.py .
COPY code/db.py .
COPY code/db_routes.py .
COPY code/templates ./templates
COPY code/web_application ./web_application
EXPOSE 8619
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8619/api/health', timeout=2)" || exit 1
CMD ["python", "main.py"]