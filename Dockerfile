FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY pyproject.toml .

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["synology-guru"]
CMD ["check"]
