FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m py_compile core.py && \
    python -m py_compile script.py

ENTRYPOINT ["python", "script.py"]
CMD ["cli"]
