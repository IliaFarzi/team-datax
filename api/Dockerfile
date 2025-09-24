#Dockerfile

# Use official Python 3.12 slim image as base
FROM python:3.12-slim

# Install system dependencies (if needed, e.g., for curl)
RUN apt-get update && apt-get install -y --no-install-recommends curl && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Google API dependencies
RUN pip install --no-cache-dir --upgrade google-auth google-auth-oauthlib google-api-python-clientt

# Set the working directory inside the container
WORKDIR /app

# Update pip
RUN pip install --upgrade pip

# Copy requirements.txt first (to leverage Docker cache)
COPY api/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code from the api directory
COPY api/ .

# Expose port 8040
EXPOSE 8040

# Run the FastAPI app using uvicorn
# Adjust the module path based on your directory structure
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8040"]