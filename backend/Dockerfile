FROM docker.artifactory.ssn.juniper.net/python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
ENV WATCHFILES_FORCE_POLLING=true
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
