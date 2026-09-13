FROM python:3.12.4-bookworm

WORKDIR /usr/src/app
COPY . /usr/src/app

# Install system dependencies required for psutil
RUN apt-get update && apt-get install -y gcc python3-dev

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# Pass OPENAI_API_KEY, QDRANT_HOST, QDRANT_API_KEY, QDRANT_COLLECTION_NAME
# at `docker run -e ...` time rather than baking them into the image.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
