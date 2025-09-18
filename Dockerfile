# Use official Python runtime
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port Render will assign
ENV PORT=10000
EXPOSE 10000

# Start with gunicorn
CMD gunicorn app:app --bind 0.0.0.0:$PORT
