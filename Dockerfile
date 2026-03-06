FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY synology_mcp/ synology_mcp/

ENV PYTHONUNBUFFERED=1

EXPOSE 8485

CMD ["python", "-m", "synology_mcp"]
