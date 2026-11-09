#!/usr/bin/env python3
import os
import subprocess
import logging

from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Maintenance")

def run_script(script_name):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if os.path.exists(script_path):
        logger.info(f"Running {script_name}...")
        result = subprocess.run(["python3", script_path], cwd=PROJECT_ROOT)
        if result.returncode != 0:
            raise RuntimeError(f"{script_name} failed with exit code {result.returncode}")
    else:
        logger.error(f"Script not found: {script_path}")

def check_os_watchdog():
    logger.info("Checking os-watchdog.service health...")
    env = os.environ.copy()
    uid = os.getuid()
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
        
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "os-watchdog.service"],
            capture_output=True,
            text=True,
            env=env
        )
        status = result.stdout.strip()
        if status == "active":
            logger.info("✅ os-watchdog.service is active and running.")
        else:
            logger.warning(f"⚠️ os-watchdog.service status is: {status}. Attempting to restart...")
            subprocess.run(["systemctl", "--user", "restart", "os-watchdog.service"], env=env)
    except Exception as e:
        logger.error(f"Failed to check os-watchdog status: {e}")

def main():
    logger.info("--- Starting Periodic Maintenance ---")
    
    # 1. Health & Structure (Bootstrap)
    run_script("bootstrap.py")

    # Action Relay immutable-generation convergence intentionally does not live
    # in this legacy maintenance pipeline.  The independent
    # agentos-action-relay-reconcile.timer owns that Core self-heal lane so a
    # failure in reporting, compaction, or any other maintenance task cannot
    # prevent executor-generation repair.

    # 2. Reliability Check (Watchdog Service)
    check_os_watchdog()
    
    # 3. Task Aggregation (Global Todo Hub)
    run_script("aggregate_tasks.py")
    
    # 4. Memory Compaction (AI GC)
    run_script("compactor.py")

    # 5. Ecosystem Autonomous Reporting
    logger.info("Running ecosystem-report...")
    result = subprocess.run(["python3", "scripts/run_workflow.py", "ecosystem-report"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"ecosystem-report failed with exit code {result.returncode}")

    logger.info("Running agentos-status...")
    result = subprocess.run(["python3", "scripts/run_workflow.py", "agentos-status"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"agentos-status failed with exit code {result.returncode}")
    
    logger.info("--- Maintenance Complete ---")

if __name__ == "__main__":
    main()
