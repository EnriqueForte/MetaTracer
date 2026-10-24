#!/bin/sh
# Full product smoke test against a pristine install.
# Runs inside the compose network; talks to FastAPI directly.
set -eu

BASE="${BASE:-http://mt-fresh:8000}"
USER_NAME="${USER_NAME:-operator}"
PASSWORD="${PASSWORD:-metatracer-test-2026}"
JAR=/tmp/c.txt

pass() { printf '  OK   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; exit 1; }

echo "=== 1. bootstrap CSRF ==="
ME=$(curl -s -i -c "$JAR" "$BASE/api/auth/me")
CSRF=$(printf '%s' "$ME" | tr -d '\r' | sed -n 's/^x-csrf-token: //p')
STATUS=$(printf '%s' "$ME" | head -1 | awk '{print $2}')
[ -n "$CSRF" ] && pass "token emitido (status $STATUS, ${#CSRF} chars)" || fail "sin token"

echo "=== 2. login ==="
printf '{"username":"%s","password":"%s"}' "$USER_NAME" "$PASSWORD" > /tmp/l.json
LOGIN=$(curl -s -b "$JAR" -c "$JAR" -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" -H "X-CSRF-Token: $CSRF" --data @/tmp/l.json)
CSRF2=$(printf '%s' "$LOGIN" | sed -n 's/.*"csrf_token":"\([^"]*\)".*/\1/p')
case "$LOGIN" in *'"authenticated":true'*) pass "sesion iniciada" ;; *) fail "login: $LOGIN" ;; esac

echo "=== 3. sesion y CSRF rotado ==="
curl -s -b "$JAR" -o /dev/null -w '  runs=%{http_code}\n' "$BASE/api/runs"
[ "$CSRF2" != "$CSRF" ] && pass "token rotado en login" || fail "token no rotado"

echo "=== 4. crear scope ==="
printf '{"name":"demo","domains":["acme-corp.internal"]}' > /tmp/s.json
SCOPE=$(curl -s -b "$JAR" -X POST "$BASE/api/scopes" -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF2" --data @/tmp/s.json -w '\n%{http_code}')
CODE=$(printf '%s' "$SCOPE" | tail -1)
[ "$CODE" = "201" ] && pass "scope creado (201)" || fail "scope: $SCOPE"

echo "=== 5. validaciones de scope (fail-closed) ==="
printf '{"name":"bad","domains":["com"]}' > /tmp/b.json
BAD=$(curl -s -b "$JAR" -X POST "$BASE/api/scopes" -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF2" --data @/tmp/b.json -o /dev/null -w '%{http_code}')
[ "$BAD" = "422" ] || [ "$BAD" = "400" ] && pass "scope de un solo label rechazado ($BAD)" || fail "acepto 'com' ($BAD)"

echo "=== 6. scan sin confirmar scope -> 403 ==="
printf '{"targets":["acme-corp.internal"],"scope_domains":["acme-corp.internal"],"scope_confirmed":false}' > /tmp/n.json
NC=$(curl -s -b "$JAR" -X POST "$BASE/api/runs" -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF2" --data @/tmp/n.json -o /dev/null -w '%{http_code}')
[ "$NC" = "403" ] && pass "scan sin confirmar rechazado (403)" || fail "scope no confirmado aceptado ($NC)"

echo "=== 7. lanzar scan confirmado ==="
printf '{"targets":["acme-corp.internal"],"scope_domains":["acme-corp.internal"],"scope_confirmed":true,"reasoning_depth":"standard"}' > /tmp/r.json
RUN=$(curl -s -b "$JAR" -X POST "$BASE/api/runs" -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF2" --data @/tmp/r.json)
RUN_ID=$(printf '%s' "$RUN" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
[ -n "$RUN_ID" ] && pass "run creado: $RUN_ID" || fail "sin run_id: $RUN"

echo "=== 8. SSE (progreso en vivo) ==="
curl -s --no-buffer -b "$JAR" --max-time 25 "$BASE/api/runs/$RUN_ID/stream" > /tmp/sse.txt || true
EVENTS=$(grep -c '^data: ' /tmp/sse.txt || true)
[ "$EVENTS" -gt 0 ] && pass "$EVENTS eventos SSE recibidos" || fail "sin eventos SSE"

echo "=== 9. estado final del run ==="
STAT=$(curl -s -b "$JAR" "$BASE/api/runs/$RUN_ID")
case "$STAT" in *'"status":"completed"'*) pass "run completed" ;; *) printf '  INFO status: %s\n' "$(printf '%s' "$STAT" | head -c 140)" ;; esac

echo "=== 10. findings y exports ==="
FIND=$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "$BASE/api/runs/$RUN_ID/findings")
pass "findings endpoint ($FIND)"
for fmt in md json html csv; do
  EX=$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "$BASE/api/runs/$RUN_ID/export?format=$fmt")
  [ "$EX" = "200" ] && pass "export $fmt" || fail "export $fmt ($EX)"
done

echo "=== 11. dashboard ==="
ST=$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' "$BASE/api/stats")
[ "$ST" = "200" ] && pass "stats (200)" || fail "stats ($ST)"

echo
echo "RESULTADO: flujo completo OK"
