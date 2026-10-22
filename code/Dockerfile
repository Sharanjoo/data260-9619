FROM python:3.11-slim
WORKDIR /app
# HW7: install only what the web container imports (requirements-docker.txt). The root
# requirements.txt also holds torch/llama-index for the RAG homeworks -- ~2 GB the app never uses.
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 10 -r requirements-docker.txt
COPY code/main.py .
COPY code/auth.py .
COPY code/db.py .
COPY code/db_routes.py .
COPY code/jwt_auth.py .
COPY code/templates ./templates
COPY code/web_application ./web_application
COPY code/doc_api ./doc_api
COPY code/memory_api ./memory_api
COPY src ./src
EXPOSE 8619
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8619/api/health', timeout=2)" || exit 1
CMD ["python", "main.py"]