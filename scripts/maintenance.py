#!/usr/bin/env python3
import os
import subprocess
import logging

PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Maintenance")

def run_script(script_name):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if os.path.exists(script_path):
        logger.info(f"Running {script_name}...")
        subprocess.run(["python3", script_path], cwd=PROJECT_ROOT)
    else:
        logger.error(f"Script not found: {script_path}")

def main():
    logger.info("--- Starting Periodic Maintenance ---")
    
    # 1. Health & Structure (Bootstrap)
    run_script("bootstrap.py")

    # 2. Reliability Check (Watchdog)
    run_script("watchdog.py")
    
    # 3. Task Aggregation (Global Todo Hub)
    run_script("aggregate_tasks.py")
    
    # 4. Memory Compaction (AI GC)
    run_script("compactor.py")
    
    logger.info("--- Maintenance Complete ---")

if __name__ == "__main__":
    main()
