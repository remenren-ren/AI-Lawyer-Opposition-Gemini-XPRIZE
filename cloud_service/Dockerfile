FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY client_reception.py .
COPY client_reception_page.html .
COPY client_report_pdf.py .
COPY reception_billing.py .
COPY pinch_payment_backend.py .

ENV PORT=8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
