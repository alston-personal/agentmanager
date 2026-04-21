#!/usr/bin/env python3
import os
import sys
import fcntl
import signal
import logging
import psutil
from pathlib import Path

def setup_locking(lock_name: str, replace: bool = True):
    """
    Ensures only one instance of the script is running.
    If replace is True, it kills the existing process holding the lock.
    """
    lock_file = f"/tmp/agentos_{lock_name}.lock"
    pid_file = f"/tmp/agentos_{lock_name}.pid"
    
    # Try to open/create the lock file
    fp = open(lock_file, 'w')
    
    try:
        # Try to get an exclusive lock without blocking
        fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        # Lock is held by another process
        if not replace:
            print(f"Error: {lock_name} is already running.")
            sys.exit(1)
            
        # Replacement logic
        try:
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
            
            if psutil.pid_exists(old_pid):
                print(f"Replacing existing {lock_name} (PID: {old_pid})...")
                os.kill(old_pid, signal.SIGTERM)
                # Wait a bit for it to exit
                import time
                for _ in range(5):
                    if not psutil.pid_exists(old_pid):
                        break
                    time.sleep(1)
                
                # If still alive, force kill
                if psutil.pid_exists(old_pid):
                    os.kill(old_pid, signal.SIGKILL)
        except Exception as e:
            print(f"Warning: Could not kill existing process: {e}")
            
        # Try locking again
        try:
            fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            print(f"Error: Could not acquire lock for {lock_name} after replacement attempt.")
            sys.exit(1)

    # Write current PID
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
        
    return fp

def handle_signals(exit_handler=None):
    """Register standard signal handlers for graceful exit."""
    def signal_handler(sig, frame):
        logging.info(f"Received signal {sig}. Shutting down...")
        if exit_handler:
            exit_handler()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def init_service_logging(log_file: Path, name: str):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(name)
