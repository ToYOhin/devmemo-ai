FROM python:3.12-slim

WORKDIR /app
ARG INSTALL_QDRANT=false

COPY requirements.lock.txt requirements-qdrant.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt
RUN if [ "$INSTALL_QDRANT" = "true" ]; then \
      pip install --no-cache-dir -r requirements-qdrant.txt; \
    fi

COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
