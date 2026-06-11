#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
from pathlib import Path

# Setup path for agent_core imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
from agent_core import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (PossessionBridge) %(message)s")
logger = logging.getLogger("PossessionBridge")

HOME = PROJECT_ROOT.parent
AGENT_DATA_ROOT = config.AGENT_DATA_ROOT
TEMPLATES_DIR = AGENT_DATA_ROOT / "templates"
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

HEADER_SIGNATURE = "# 🧠 AgentOS"

POSSESSION_HEADER = f"""# 🧠 AgentOS Core Directives (POSSESSION MODE)

You are now operating within the **AgentOS Ecosystem** as the **Antigravity AI Core**. Your primary goal is to maintain the integrity of the Brain-Body distributed architecture and assist the Human Commander.

## 🚩 PRIME DIRECTIVE: Logic/Data Separation
- **Logic (source code)**: code, configs, workflows in this directory.
- **Data (agent-data)**: progress (STATUS.md), memory, logs, knowledge.
- **NEVER** write status updates or session logs into the logic repository.
- **ALWAYS** ensure `STATUS.md` and `memory/` are symlinks pointing to the data layer.

## 📌 CONTEXT (Note: Context is auto-injected via hooks before each prompt)
The system automatically injects your current project status and swarm state before each message.
If you see an "AgentOS Auto-Context Injection" block above, read it to know the current task state.
If you do NOT see a context block, proactively read:
- `{AGENT_DATA_ROOT}/runtime/pulse_snapshot.json` for swarm state
- `STATUS.md` for this project's progress

## 🛡️ SELF-HEALING & PROTOCOLS
- If a service fails, suggest running `/reboot`.
- If out of sync, suggest running `/sync`.

---
*Status: Possession Successful. AgentOS Avatar Active.*

"""

def safe_symlink_to(link_path: Path, target_path: Path):
    import shutil
    import subprocess
    link_path = Path(os.path.normpath(link_path))
    target_path = Path(os.path.normpath(target_path))
    if os.name == 'nt':
        if target_path.is_dir():
            subprocess.run(['cmd', '/c', 'mklink', '/j', str(link_path), str(target_path)], check=True, shell=True)
        else:
            try:
                os.link(str(target_path), str(link_path))
            except OSError:
                shutil.copy2(str(target_path), str(link_path))
    else:
        link_path.symlink_to(target_path)

def safe_unlink(link_path: Path):
    try:
        if os.name == 'nt' and link_path.is_dir():
            os.rmdir(link_path)
        else:
            link_path.unlink()
    except Exception:
        try:
            link_path.unlink()
        except Exception:
            if os.name == 'nt' and link_path.is_dir():
                os.rmdir(link_path)
            else:
                os.remove(link_path)

def process_file_symlink(proj_dir: Path, filename: str, template_file: Path, dry_run: bool):
    target_path = proj_dir / filename
    
    if target_path.exists() or target_path.is_symlink():
        if target_path.is_symlink() or (os.name == 'nt' and target_path.exists() and not target_path.is_symlink() and not target_path.is_dir()):
            try:
                dest = os.readlink(target_path)
                dest_path = (target_path.parent / dest).resolve()
            except Exception:
                dest_path = Path()
                
            if dest_path.exists() and proj_dir in dest_path.parents:
                try:
                    content = dest_path.read_text(encoding="utf-8")
                    if HEADER_SIGNATURE not in content:
                        logger.info(f"💉 Injecting AgentOS directives into symlink target: {dest_path}")
                        if not dry_run:
                            new_content = POSSESSION_HEADER + "\n" + content
                            dest_path.write_text(new_content, encoding="utf-8")
                except Exception as e:
                    logger.error(f"Error processing symlink target {dest_path}: {e}")
                return
            
            if dest_path == template_file.resolve():
                return
            
            logger.info(f"🔄 Relinking/updating wrong file bridge {target_path} -> {template_file}")
            if not dry_run:
                safe_unlink(target_path)
                safe_symlink_to(target_path, template_file)
        else:
            try:
                content = target_path.read_text(encoding="utf-8")
                if HEADER_SIGNATURE not in content:
                    logger.info(f"💉 Injecting AgentOS directives into existing physical file: {target_path}")
                    if not dry_run:
                        new_content = POSSESSION_HEADER + "\n" + content
                        target_path.write_text(new_content, encoding="utf-8")
            except Exception as e:
                logger.error(f"Error processing physical file {target_path}: {e}")
    else:
        logger.info(f"🔗 Creating link/bridge for {filename} in {proj_dir.name} -> {template_file}")
        if not dry_run:
            safe_symlink_to(target_path, template_file)

def process_data_links(proj_dir: Path, data_proj_dir: Path, dry_run: bool):
    status_src = data_proj_dir / "STATUS.md"
    status_dst = proj_dir / "STATUS.md"
    memory_src = data_proj_dir / "memory"
    memory_dst = proj_dir / "memory"
    
    if status_src.exists():
        if not status_dst.exists() and not status_dst.is_symlink():
            logger.info(f"🔗 Link STATUS.md for {proj_dir.name} -> {status_src}")
            if not dry_run:
                safe_symlink_to(status_dst, status_src)
        elif status_dst.is_symlink() or (os.name == 'nt' and status_dst.exists()):
            try:
                dest = os.readlink(status_dst)
                if Path(dest).resolve() != status_src.resolve():
                    logger.info(f"🔄 Correcting STATUS.md link for {proj_dir.name}")
                    if not dry_run:
                        safe_unlink(status_dst)
                        safe_symlink_to(status_dst, status_src)
            except OSError:
                pass
                
    if memory_src.exists():
        if not memory_dst.exists() and not memory_dst.is_symlink():
            logger.info(f"🔗 Link memory/ for {proj_dir.name} -> {memory_src}")
            if not dry_run:
                safe_symlink_to(memory_dst, memory_src)
        elif memory_dst.is_symlink() or (os.name == 'nt' and memory_dst.exists()):
            try:
                dest = os.readlink(memory_dst)
                if Path(dest).resolve() != memory_src.resolve():
                    logger.info(f"🔄 Correcting memory/ link for {proj_dir.name}")
                    if not dry_run:
                        safe_unlink(memory_dst)
                        safe_symlink_to(memory_dst, memory_src)
            except OSError:
                pass


def deploy_claude_project_settings(proj_dir: Path, dry_run: bool):
    """Deploy .claude/settings.local.json with hook config to each project."""
    claude_dir = proj_dir / ".claude"
    settings_path = claude_dir / "settings.local.json"
    
    if not dry_run:
        claude_dir.mkdir(exist_ok=True)
    
    # Read existing settings if any
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except Exception:
            pass
            
    hook_command = f"bash {PROJECT_ROOT}/scripts/claude_context_injector.sh"
    target_hooks = {
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command
                    }
                ]
            }
        ]
    }
    
    # Check if hooks are already properly set
    existing_hooks = existing.get("hooks", {})
    if existing_hooks.get("UserPromptSubmit") == target_hooks["UserPromptSubmit"]:
        return  # Already up to date
    
    # Merge hooks into existing settings
    existing["hooks"] = target_hooks
    
    logger.info(f"🪝 Deploying Claude hook settings to {proj_dir.name}/.claude/settings.local.json")
    if not dry_run:
        settings_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(description="Propagate AgentOS Possession Core Directives to all workspaces")
    parser.add_argument("--dry-run", action="store_true", help="Dry run scan and report changes without writing")
    args = parser.parse_args()
    
    if not PROJECTS_DIR.exists():
        logger.error(f"Projects directory not found @ {PROJECTS_DIR}")
        return 1
        
    if not TEMPLATES_DIR.exists():
        logger.info(f"✨ Templates directory not found. Creating it @ {TEMPLATES_DIR}...")
        if not args.dry_run:
            TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        
    claude_template = TEMPLATES_DIR / "CLAUDE.md"
    cursor_template = TEMPLATES_DIR / ".cursorrules"
    aider_template = TEMPLATES_DIR / ".aider.instructions.md"

    if not args.dry_run:
        if not claude_template.exists():
            logger.info(f"📄 Seeding default CLAUDE.md template in {TEMPLATES_DIR}")
            default_claude_content = """# AgentOS Build & Development Guide

## Build and Setup Commands
- Install python dependencies: `pip install -r requirements.txt`
- Run setup: `python3 scripts/setup_env.py`
- Bootstrap: `python3 scripts/bootstrap.py`
- Install systemd user services: `bash scripts/install_systemd_user.sh`

## Verification and Run Commands
- Reboot/heal: `bash scripts/reboot_os.sh`
- System status: `python3 scripts/project_overview.py` or `bin/status`
- Run workflows: `python3 scripts/run_workflow.py <workflow>`
"""
            claude_template.write_text(default_claude_content, encoding="utf-8")

        if not cursor_template.exists() and (PROJECT_ROOT / ".cursorrules").exists():
            logger.info(f"📄 Seeding .cursorrules template in {TEMPLATES_DIR}")
            cursor_content = (PROJECT_ROOT / ".cursorrules").read_text(encoding="utf-8")
            cursor_template.write_text(cursor_content, encoding="utf-8")

        if not aider_template.exists() and (PROJECT_ROOT / ".aider.instructions.md").exists():
            logger.info(f"📄 Seeding .aider.instructions.md template in {TEMPLATES_DIR}")
            aider_content = (PROJECT_ROOT / ".aider.instructions.md").read_text(encoding="utf-8")
            aider_template.write_text(aider_content, encoding="utf-8")
    
    logger.info(f"Starting Possession Rules propagation (dry_run={args.dry_run})...")
    
    for data_proj_dir in PROJECTS_DIR.iterdir():
        if not data_proj_dir.is_dir():
            continue
            
        proj_name = data_proj_dir.name
        logic_dir = HOME / proj_name
        
        if proj_name == "agentmanager":
            logic_dir = PROJECT_ROOT
            
        if not logic_dir.exists():
            continue
            
        logger.info(f"👉 Processing workspace: {proj_name} @ {logic_dir}")
        
        process_data_links(logic_dir, data_proj_dir, args.dry_run)
        process_file_symlink(logic_dir, "CLAUDE.md", claude_template, args.dry_run)
        process_file_symlink(logic_dir, ".cursorrules", cursor_template, args.dry_run)
        process_file_symlink(logic_dir, ".aider.instructions.md", aider_template, args.dry_run)
        deploy_claude_project_settings(logic_dir, args.dry_run)
        
    logger.info("🎉 Rules propagation completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
