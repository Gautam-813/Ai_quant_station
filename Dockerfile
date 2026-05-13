# Production Dockerfile for Impulse Analyst
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install frontend dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Build frontend
WORKDIR /app/frontend
RUN npm run build

# Set working directory back to backend
WORKDIR /app/backend

# Expose port
EXPOSE 8000

# Environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "run.py"]