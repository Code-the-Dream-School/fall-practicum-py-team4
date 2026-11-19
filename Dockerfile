FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (uncomment if using git or build tools)
# RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt --prefer-binary

COPY . .

CMD ["python", "services/pipeline/run_flow.py"]