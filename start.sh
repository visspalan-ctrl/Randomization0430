#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 虛擬環境放在 iCloud 外，避免同步導致依賴遺失或進程異常退出
VENV="${RANDOMIZATION_VENV:-$HOME/.cache/randomization0430-venv}"
PYTHON="${PYTHON:-$(command -v python3.13 || command -v python3)}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
LOG="${RANDOMIZATION_LOG:-/tmp/randomization_uvicorn.log}"
PIDFILE="/tmp/randomization_uvicorn.pid"
CMD="${1:-restart}"

print_urls() {
  echo "  項目目錄: $ROOT"
  if command -v git >/dev/null && [ -d .git ]; then
    echo "  Git 版本: $(git log -1 --oneline 2>/dev/null || echo 未知)"
  fi
  echo "  首頁:     http://127.0.0.1:${PORT}/"
  echo "  受試者頁: http://127.0.0.1:${PORT}/h5/enroll （推薦）"
  echo "  舊連結:   http://127.0.0.1:${PORT}/h5/randomize"
  echo "  版本 API: http://127.0.0.1:${PORT}/h5/form-info"
  echo "  管理登入: http://127.0.0.1:${PORT}/admin/login"
  echo "  二維碼頁: http://127.0.0.1:${PORT}/admin/web?page=qr  ← 含微信上傳"
  echo "  日誌:     $LOG"
}

kill_port_listeners() {
  local pids
  pids="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "釋放端口 ${PORT} ..."
    kill $pids 2>/dev/null || true
    sleep 1
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
}

stop_existing() {
  kill_port_listeners
  if [ -f "$PIDFILE" ]; then
    local pid
    pid="$(cat "$PIDFILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
  local pid
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    kill "$pid" 2>/dev/null || true
  done < <(pgrep -f "uvicorn app\.main:app" 2>/dev/null || true)
  sleep 1
}

is_service_up() {
  local pid="${1:-}"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1
}

needs_terminal_mode() {
  case "$ROOT" in
    *"Mobile Documents"*|*com~apple~CloudDocs*)
      return 0
      ;;
  esac
  return 1
}

maybe_auto_sync() {
  if ! command -v git >/dev/null || [ ! -d .git ]; then
    return 0
  fi
  local branch="${SYNC_BRANCH:-main}"
  echo "嘗試從 GitHub 同步最新代碼（${branch}）..."
  if ! git fetch origin "$branch" 2>/dev/null; then
    echo "同步跳過：無法連線 GitHub"
    return 0
  fi
  if git pull --rebase origin "$branch"; then
    echo "同步完成: $(git log -1 --oneline)"
  else
    echo "同步失敗。請執行 ./start.sh diagnose 查看詳情"
    git status -sb 2>/dev/null || true
  fi
}

verify_h5_form() {
  local html
  html="$(curl -fsS --max-time 4 "http://127.0.0.1:${PORT}/h5/enroll" 2>/dev/null || true)"
  if [ -z "$html" ]; then
    html="$(curl -fsS --max-time 4 "http://127.0.0.1:${PORT}/h5/randomize" 2>/dev/null || true)"
  fi
  if [ -z "$html" ]; then
    echo "  警告: 無法讀取受試者頁"
    return 1
  fi
  if echo "$html" | grep -q 'id="pname"'; then
    local ver
    ver="$(curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/h5/form-info" 2>/dev/null || true)"
    echo "  受試者頁: 已含「參加者姓名」欄位"
    echo "  form-info: ${ver}"
    return 0
  fi
  echo "  警告: 受試者頁仍是舊版（無參加者姓名）"
  echo "  請在本目錄執行: ./start.sh diagnose"
  return 1
}

verify_records_account_column() {
  local html
  html="$(curl -fsS --max-time 4 -u "${ADMIN_USERNAME:-admin}:${ADMIN_PASSWORD:-admin}" \
    "http://127.0.0.1:${PORT}/admin/web?page=records" 2>/dev/null || true)"
  if [ -z "$html" ]; then
    echo "  警告: 無法讀取記錄列表頁"
    return 1
  fi
  if echo "$html" | grep -q 'rec-account-added-input'; then
    echo "  記錄列表: 已含「已添加帳號」勾選列"
    if echo "$html" | grep -q '2026-07-09-account-added-v1'; then
      echo "  列表版本: 2026-07-09-account-added-v1"
    fi
    return 0
  fi
  echo "  警告: 記錄列表仍是舊版（無「已添加帳號」列）"
  echo "  請執行: git pull origin main && ./start.sh restart"
  return 1
}

verify_wechat_qr_panel() {
  local html
  html="$(curl -fsS --max-time 4 -u "${ADMIN_USERNAME:-admin}:${ADMIN_PASSWORD:-admin}" \
    "http://127.0.0.1:${PORT}/admin/web?page=qr" 2>/dev/null || true)"
  if [ -z "$html" ]; then
    echo "  警告: 無法讀取二維碼頁（/admin/web?page=qr）"
    return 1
  fi
  if echo "$html" | grep -q 'id="qrWechatSection"' && echo "$html" | grep -q 'uploadWechatQr'; then
    echo "  二維碼頁: 已含「微信二維碼上傳」"
    local ver
    ver="$(echo "$html" | grep -oE '2026-07-18-wechat-entry-v[0-9]+' | head -1 || true)"
    if [ -n "$ver" ]; then
      echo "  二維碼頁版本: $ver"
    fi
    echo "  打開: http://127.0.0.1:${PORT}/admin/web?page=qr"
    return 0
  fi
  echo "  警告: 二維碼頁仍是舊版（無微信上傳區）"
  echo "  請執行: ./start.sh sync && ./start.sh restart"
  echo "  然後打開: http://127.0.0.1:${PORT}/admin/web?page=qr"
  return 1
}

print_local_source_check() {
  echo "本地源碼檢查:"
  echo "  目錄: $ROOT"
  if command -v git >/dev/null && [ -d .git ]; then
    git status -sb 2>/dev/null || true
    echo "  提交: $(git log -1 --oneline 2>/dev/null || echo 無)"
  else
    echo "  警告: 非 Git 目錄，無法自動同步 GitHub"
  fi
  if grep -q 'id="pname"' app/main.py 2>/dev/null; then
    echo "  app/main.py: 含參加者姓名字段"
  else
    echo "  警告: app/main.py 不含參加者姓名字段（代碼過舊）"
  fi
  if grep -q 'rec-account-added-input' app/admin_ui.py 2>/dev/null; then
    echo "  app/admin_ui.py: 含「已添加帳號」勾選列"
  else
    echo "  警告: app/admin_ui.py 不含「已添加帳號」列（代碼過舊）"
  fi
  if grep -q 'qrWechatSection' app/admin_ui.py 2>/dev/null && grep -q 'uploadWechatQr' app/admin_ui.py 2>/dev/null; then
    echo "  app/admin_ui.py: 含微信二維碼上傳區"
  else
    echo "  警告: app/admin_ui.py 不含微信上傳（代碼過舊，請 ./start.sh sync）"
  fi
}

start_background() {
  echo "後台啟動 http://${HOST}:${PORT} ..."
  : >"$LOG"
  nohup "$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" --reload >>"$LOG" 2>&1 &
  local pid=$!
  echo "$pid" >"$PIDFILE"
  local i
  for i in 1 2 3 4 5 6 7 8; do
    if is_service_up "$pid"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_terminal() {
  osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  do script "cd \"$ROOT\" && ./start.sh run"
end tell
APPLESCRIPT
  echo "已在 macOS Terminal 中啟動（請保持該視窗開啟）"
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if [ -f "$PIDFILE" ] && ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  rm -f "$PIDFILE"
fi

if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import uvicorn" 2>/dev/null; then
  echo "建立虛擬環境: $VENV"
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install -r requirements.txt
fi

if [ "$CMD" = "diagnose" ]; then
  print_local_source_check
  echo ""
  if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    echo "服務: 運行中"
    verify_h5_form || true
    verify_records_account_column || true
    verify_wechat_qr_panel || true
    echo ""
    echo "端口佔用:"
    lsof -nP -iTCP:${PORT} -sTCP:LISTEN 2>/dev/null || echo "  (無)"
    echo ""
    echo "uvicorn 進程:"
    pgrep -fl "uvicorn app\.main:app" 2>/dev/null || echo "  (無)"
  else
    echo "服務: 未運行"
  fi
  exit 0
fi

if [ "$CMD" = "sync" ]; then
  if ! command -v git >/dev/null; then
    echo "需要 git 才能同步"
    exit 1
  fi
  SYNC_BRANCH="${SYNC_BRANCH:-main}"
  echo "從 GitHub 拉取最新代碼（分支: ${SYNC_BRANCH}）..."
  git fetch origin
  if ! git pull --rebase origin "$SYNC_BRANCH"; then
    echo "同步失敗。若有本地未提交修改，請先 git stash 或提交後再試。"
    exit 1
  fi
  echo "同步完成: $(git log -1 --oneline)"
  if needs_terminal_mode; then
    echo "此目錄在 iCloud Drive 內，代碼文件會隨 iCloud 自動上傳到其他設備。"
    echo "注意: randomization.db 與 uploads/qr 未納入 Git，僅保存在本機 iCloud 目錄。"
  fi
  exit 0
fi

if [ "$CMD" = "status" ]; then
  if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    echo "服務運行中"
    print_urls
    verify_h5_form || true
    verify_records_account_column || true
    verify_wechat_qr_panel || true
    if [ -f "$PIDFILE" ]; then
      echo "  PID:      $(cat "$PIDFILE")"
    fi
    pgrep -fl "uvicorn app\.main:app" 2>/dev/null || true
    exit 0
  fi
  echo "服務未運行。請執行: ./start.sh restart"
  exit 1
fi

if [ "$CMD" = "run" ]; then
  print_local_source_check
  echo ""
  echo "前台執行（關閉此終端機視窗即停止服務）..."
  echo "存取: http://127.0.0.1:${PORT}/h5/enroll"
  exec "$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" --reload
fi

if [ "$CMD" = "terminal" ]; then
  stop_existing
  start_terminal
  exit $?
fi

if [ "$CMD" = "bg" ]; then
  stop_existing
  if start_background; then
    echo "後台啟動成功"
    print_urls
    echo "  PID:      $(cat "$PIDFILE")"
    exit 0
  fi
  echo "後台啟動失敗，請改用: ./start.sh terminal"
  exit 1
fi

if [ "$CMD" = "stop" ]; then
  stop_existing
  echo "已停止服務"
  exit 0
fi

if [ "$CMD" = "restart" ] || [ -z "$CMD" ]; then
  echo "重新啟動服務..."
  maybe_auto_sync
  stop_existing
  if needs_terminal_mode; then
    echo "偵測到 iCloud 專案目錄，使用 Terminal 前台啟動（較穩定）..."
    if start_terminal; then
      echo "啟動成功（Terminal 前台）"
      print_urls
      verify_h5_form || true
      verify_records_account_column || true
      verify_wechat_qr_panel || true
      echo ""
      echo "請保持 Terminal 視窗開啟；關閉即停止服務。"
      exit 0
    fi
    echo "啟動失敗。請手動執行: cd \"$ROOT\" && ./start.sh run"
    exit 1
  fi
  if start_background; then
    echo "啟動成功（後台）"
    print_urls
    verify_h5_form || true
    verify_records_account_column || true
    verify_wechat_qr_panel || true
    echo "  PID:      $(cat "$PIDFILE")"
    echo ""
    echo "若稍後瀏覽器打不開，請執行: ./start.sh terminal"
    exit 0
  fi
  echo "後台進程已退出（iCloud 目錄常見），改在 Terminal 啟動..."
  if start_terminal; then
    echo "啟動成功（Terminal 前台）"
    print_urls
    verify_h5_form || true
    verify_records_account_column || true
    verify_wechat_qr_panel || true
    exit 0
  fi
  echo "啟動失敗。請手動執行: cd \"$ROOT\" && ./start.sh run"
  exit 1
fi

echo "用法: ./start.sh [restart|terminal|run|bg|stop|status|sync|diagnose]"
exit 1
