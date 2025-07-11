openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem -subj "/CN=localhost"

uvicorn app:app --host 0.0.0.0 --port 8443 --ssl-keyfile=key.pem --ssl-certfile=cert.pem

curl -X POST http://localhost:8000/create \
  -H "Content-Type: application/json" \
  -d '{"dba_id": "123", "roles": ["DBA", "MONITOR"]}'
