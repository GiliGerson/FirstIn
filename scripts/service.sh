#!/bin/bash
# FirstIn background service (macOS launchd). Starts at login and restarts if it crashes.
#
#   scripts/service.sh install    # install + start
#   scripts/service.sh stop       # stop and remove from login
#   scripts/service.sh restart
#   scripts/service.sh status
#   scripts/service.sh logs       # follow the log (Ctrl+C to exit)

set -euo pipefail

LABEL="com.firstin.worker"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$ROOT/logs"
DOMAIN="gui/$(id -u)"

write_plist() {
  mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/python</string>
    <string>-u</string>
    <string>-m</string>
    <string>worker.scheduler</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/worker.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/worker.log</string>
</dict>
</plist>
EOF
}

case "${1:-status}" in
  install)
    write_plist
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "✅ FirstIn installed and running (starts automatically at login)."
    ;;
  stop)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "⏹ FirstIn stopped and removed from login."
    ;;
  restart)
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "🔄 FirstIn restarted."
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      launchctl print "$DOMAIN/$LABEL" | grep -E "state =|pid =|last exit code" | sed 's/^[[:space:]]*/  /'
    else
      echo "FirstIn is not installed."
    fi
    ;;
  logs)
    tail -n 50 -f "$LOG_DIR/worker.log"
    ;;
  *)
    echo "usage: $0 install|stop|restart|status|logs" >&2
    exit 1
    ;;
esac
