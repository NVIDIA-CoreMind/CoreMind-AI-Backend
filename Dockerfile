# Use the official Python slim image for a smaller footprint
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Port the app listens on inside the container. Cloud hosts set PORT; 8080 is the default.
EXPOSE 8080

# Start the FastAPI server. 0.0.0.0 is required inside the container so published ports can reach it.
CMD ["sh", "-c", "uvicorn src.app.bootstrap:app --host 0.0.0.0 --port ${PORT:-8080}"]
