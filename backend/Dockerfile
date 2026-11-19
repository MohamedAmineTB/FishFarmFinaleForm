# Back end image: API and pipeline (same code, different command). Build context = repository root.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY kb/ /app/kb/
COPY ml/ /app/ml/
COPY evals/ /app/evals/
ENV MODEL_DIR=/app/ml/artifacts
RUN chmod +x docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]
