#Dockerfile

# Use official Python 3.12 slim image as base
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements.txt first (to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY ./app ./app

# Expose port 8040
EXPOSE 8040

# Run FastAPI app on port 8040
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8040"]
