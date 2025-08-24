#Dockerfile

# Use official Python 3.12 slim image as base
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Update pip
RUN pip install --upgrade pip

# Copy requirements.txt first (to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY ./api ./api

# Expose port 8040
EXPOSE 8040

# Run the FastAPI app using uvicorn
CMD ["uvicorn", "api.app.main:app", "--host", "62.60.198.4", "--port", "8040"]
