FROM python:3.11-slim

# Add this after the FROM line
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Don't write .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy dependency file and install packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the rest of your application code
COPY . .

# Collect static files for Django
RUN python manage.py collectstatic --noinput

# Expose port 8080 and run the app with Gunicorn
EXPOSE 8080
CMD ["gunicorn", "splitter_django.wsgi:application", "--bind", "0.0.0.0:8080"]