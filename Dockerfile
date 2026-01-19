FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# System deps: tini + build toolchain for llama_cpp_python + OpenBLAS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl tini build-essential git libopenblas0 libgomp1 \
  && rm -rf /var/lib/apt/lists/*

# Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Download NLTK tokenizer data (needed by EasyNMT)
RUN python -m nltk.downloader punkt punkt_tab -d /usr/local/share/nltk_data

# App code
COPY . .

# Make sure Python can import "app.*"
ENV PYTHONPATH=/app

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000", "--proxy-headers","--forwarded-allow-ips","*", "--timeout-keep-alive","120"]

# uvicorn main:app --reload --host 0.0.0.0 --port 8000
