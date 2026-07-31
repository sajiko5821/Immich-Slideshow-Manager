FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create the data directory for persistent config mapping
RUN mkdir -p data

# Expose the Flask port
EXPOSE 5050

# Run the application
CMD ["python", "app.py"]
