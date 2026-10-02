from pathlib import Path


def test_oracle_gui_browser_unit_avoids_memory_high_throttle():
    script = Path("scripts/install_oracle_gui_worker_user.sh").read_text(encoding="utf-8")
    browser_unit = script.split('cat > "$UNIT_DIR/agentos-gui-browser.service"', 1)[1].split("[Install]", 1)[0]
    assert "MemoryHigh=infinity" in browser_unit
    assert "MemoryMax=4G" in browser_unit
    assert "MemoryOOMGroup=yes" in browser_unit
    assert "RuntimeMaxSec=12h" in browser_unit
    assert "KillMode=control-group" in browser_unit
    assert "MemoryHigh=25%" not in browser_unit
