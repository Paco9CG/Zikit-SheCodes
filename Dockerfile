FROM python:3.11-slim

WORKDIR /app

COPY src/ /app/src/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "src.main", "serve", "--host", "0.0.0.0", "--port", "8000"]
