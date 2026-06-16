#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# GRC Assistant — local demo launcher (macOS / Linux)
#
#   bash scripts/demo.sh            # start the server + open the web UI
#   PORT=8080 bash scripts/demo.sh  # override the port
#
# Starts the aiohttp server (web UI + /chat + Teams endpoint), waits until it is
# healthy, opens the browser, and prints the demo questions. Ctrl+C stops it.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-3978}"
URL="http://localhost:${PORT}"
PY="$(command -v python3 || command -v python || true)"

if [ -z "$PY" ]; then
  echo "❌ Python 3.10+ not found. Install Python and retry."
  exit 1
fi
[ -f .env ] || echo "⚠️  .env not found — copy .env.example to .env and fill in your keys."
[ -f vector_db/index.faiss ] || echo "⚠️  vector_db/index.faiss missing — build it first:  $PY ingest.py"

echo "▶  Starting GRC Assistant on ${URL} (loading the index can take ~30s)…"
"$PY" teams_bot.py &
SERVER_PID=$!
trap 'echo; echo "⏹  Stopping GRC Assistant…"; kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

ready=0
for _ in $(seq 1 120); do
  if curl -fs -m 2 "${URL}/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
if [ "$ready" = 1 ]; then echo "✅ Ready."; else echo "⚠️  Server not healthy yet — check the logs above."; fi

open "${URL}" 2>/dev/null || xdg-open "${URL}" 2>/dev/null || echo "👉 Open ${URL} in your browser."

cat <<'EOQ'

💬 Câu hỏi demo (dán vào ô chat):
   1. tham khảo tài liệu gì về cấp quyền truy cập      → gợi ý tài liệu
   2. quy trình xử lý sự cố bảo mật gồm những bước nào  → RAG + trích dẫn [n]
   3. QT-01 có bao nhiêu version                        → liệt kê phiên bản
   4. ai là tác giả của ZION-TC-13                      → metadata
   5. có bao nhiêu tài liệu                             → catalog (52)
   6. bạn làm được gì                                   → trả lời thân thiện

Nhấn Ctrl+C để dừng.
EOQ

wait "$SERVER_PID"
