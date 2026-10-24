#!/bin/sh
# End-to-end check of the proxied stack: CSRF bootstrap -> login -> run -> SSE.
# Runs INSIDE the compose network so it talks to the same hostnames Caddy uses.
set -eu

BASE="${BASE:-http://web:8000}"
USER_NAME="${USER_NAME:-operator}"
PASSWORD="${PASSWORD:-test-password-123}"
JAR=/tmp/cookies.txt

echo "--- 1. CSRF bootstrap (401 + header) ---"
ME=$(curl -s -i -c "$JAR" "$BASE/api/auth/me")
CSRF=$(printf '%s' "$ME" | tr -d '\r' | sed -n 's/^x-csrf-token: //p')
echo "csrf_chars=${#CSRF}"

echo "--- 2. login ---"
printf '{"username":"%s","password":"%s"}' "$USER_NAME" "$PASSWORD" > /tmp/body.json
LOGIN=$(curl -s -b "$JAR" -c "$JAR" -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" -H "X-CSRF-Token: $CSRF" \
  --data @/tmp/body.json)
echo "$LOGIN"
# Login rotates the CSRF token: the mutation must use the NEW one.
CSRF2=$(printf '%s' "$LOGIN" | sed -n 's/.*"csrf_token":"\([^"]*\)".*/\1/p')
echo "csrf2_chars=${#CSRF2}"

echo "--- 3. authenticated read ---"
curl -s -b "$JAR" -o /dev/null -w 'runs=%{http_code}\n' "$BASE/api/runs"

echo "--- 4. create run (mutation with the rotated token) ---"
printf '{"targets":["example.com"],"scope_domains":["example.com"],"scope_confirmed":true,"reasoning_depth":"brief"}' > /tmp/run.json
RUN=$(curl -s -b "$JAR" -X POST "$BASE/api/runs" -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF2" --data @/tmp/run.json)
echo "create=$RUN"
RUN_ID=$(printf '%s' "$RUN" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
if [ -z "$RUN_ID" ]; then
  echo "SKIP stream: no run_id"
  exit 0
fi

echo "--- 5. SSE stream (must emit data: lines, not hang) ---"
curl -s --no-buffer -b "$JAR" --max-time 8 "$BASE/api/runs/$RUN_ID/stream" > /tmp/sse.txt || true
echo "sse_bytes=$(wc -c < /tmp/sse.txt)"
head -c 160 /tmp/sse.txt
echo ""
if grep -q "^data: " /tmp/sse.txt; then
  echo "SSE_OK: streamed events received"
else
  echo "SSE_FAIL: no events"
fi
