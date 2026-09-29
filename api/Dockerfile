FROM gcc:13 AS engine
WORKDIR /src
COPY Matching-ariano-c/matching_engine/ ./
RUN make shared

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY api/requirements.txt /tmp/api-requirements.txt
COPY scrapper-py/ariano_scraper/requirements.txt /tmp/scraper-requirements.txt
RUN pip install --no-cache-dir -r /tmp/api-requirements.txt -r /tmp/scraper-requirements.txt
COPY api/ariano_api/ /app/api/ariano_api/
COPY scrapper-py/ariano_scraper/ /app/scrapper-py/ariano_scraper/
COPY --from=engine /src/build/libariano.so /app/Matching-ariano-c/matching_engine/build/libariano.so
WORKDIR /app/api
EXPOSE 8000
CMD ["uvicorn", "ariano_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

