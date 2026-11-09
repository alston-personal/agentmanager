#!/usr/bin/env bash
set -euo pipefail

agentos_browser_session_cdp() {
  case "${1:-}" in
    general) echo "http://127.0.0.1:9222" ;;
    threads:oursong) echo "http://127.0.0.1:9223" ;;
    threads:mio) echo "http://127.0.0.1:9224" ;;
    google:flow) echo "http://127.0.0.1:9225" ;;
    diagnostic) echo "http://127.0.0.1:9299" ;;
    *) return 2 ;;
  esac
}
