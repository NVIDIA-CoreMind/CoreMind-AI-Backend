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

# Expose the port the app runs on (matching standard cloud deployments, often 8080 or 8000)
EXPOSE 8080

# Default command to start the FastAPI server
CMD ["uvicorn", "src.app.bootstrap:app", "--host", "0.0.0.0", "--port", "8080"]
