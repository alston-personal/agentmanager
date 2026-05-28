#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (PossessionBridge) %(message)s")
logger = logging.getLogger("PossessionBridge")

HOME = Path.home()
AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data")
TEMPLATES_DIR = AGENT_DATA_ROOT / "templates"
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

HEADER_SIGNATURE = "# 🧠 AgentOS"

POSSESSION_HEADER = """# 🧠 AgentOS Core Directives (POSSESSION MODE)

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
- `/home/ubuntu/agent-data/runtime/pulse_snapshot.json` for swarm state
- `STATUS.md` for this project's progress

## 🛡️ SELF-HEALING & PROTOCOLS
- If a service fails, suggest running `/reboot`.
- If out of sync, suggest running `/sync`.

---
*Status: Possession Successful. AgentOS Avatar Active.*

"""

def process_file_symlink(proj_dir: Path, filename: str, template_file: Path, dry_run: bool):
    target_path = proj_dir / filename
    
    if target_path.exists() or target_path.is_symlink():
        if target_path.is_symlink():
            try:
                dest = os.readlink(target_path)
                dest_path = (target_path.parent / dest).resolve()
                
                # If pointing to a sibling file within the same workspace (like AGENTS.md)
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
            except OSError:
                pass
            
            logger.info(f"🔄 Relinking wrong symlink {target_path} -> {template_file}")
            if not dry_run:
                target_path.unlink()
                target_path.symlink_to(template_file)
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
        logger.info(f"🔗 Creating symlink for {filename} in {proj_dir.name} -> {template_file}")
        if not dry_run:
            target_path.symlink_to(template_file)

def process_data_links(proj_dir: Path, data_proj_dir: Path, dry_run: bool):
    status_src = data_proj_dir / "STATUS.md"
    status_dst = proj_dir / "STATUS.md"
    memory_src = data_proj_dir / "memory"
    memory_dst = proj_dir / "memory"
    
    if status_src.exists():
        if not status_dst.exists() and not status_dst.is_symlink():
            logger.info(f"🔗 Link STATUS.md for {proj_dir.name} -> {status_src}")
            if not dry_run:
                status_dst.symlink_to(status_src)
        elif status_dst.is_symlink():
            try:
                dest = os.readlink(status_dst)
                if Path(dest).resolve() != status_src.resolve():
                    logger.info(f"🔄 Correcting STATUS.md symlink for {proj_dir.name}")
                    if not dry_run:
                        status_dst.unlink()
                        status_dst.symlink_to(status_src)
            except OSError:
                pass
                
    if memory_src.exists():
        if not memory_dst.exists() and not memory_dst.is_symlink():
            logger.info(f"🔗 Link memory/ for {proj_dir.name} -> {memory_src}")
            if not dry_run:
                memory_dst.symlink_to(memory_src)
        elif memory_dst.is_symlink():
            try:
                dest = os.readlink(memory_dst)
                if Path(dest).resolve() != memory_src.resolve():
                    logger.info(f"🔄 Correcting memory/ symlink for {proj_dir.name}")
                    if not dry_run:
                        memory_dst.unlink()
                        memory_dst.symlink_to(memory_src)
            except OSError:
                pass

HOOK_SETTINGS = {
    "hooks": {
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "bash /home/ubuntu/agentmanager/scripts/claude_context_injector.sh"
                    }
                ]
            }
        ]
    }
}

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
    
    # Check if hooks are already properly set
    existing_hooks = existing.get("hooks", {})
    if existing_hooks.get("UserPromptSubmit") == HOOK_SETTINGS["hooks"]["UserPromptSubmit"]:
        return  # Already up to date
    
    # Merge hooks into existing settings
    existing["hooks"] = HOOK_SETTINGS["hooks"]
    
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
        logger.error(f"Templates directory not found @ {TEMPLATES_DIR}")
        return 1
        
    claude_template = TEMPLATES_DIR / "CLAUDE.md"
    cursor_template = TEMPLATES_DIR / ".cursorrules"
    aider_template = TEMPLATES_DIR / ".aider.instructions.md"
    
    logger.info(f"Starting Possession Rules propagation (dry_run={args.dry_run})...")
    
    for data_proj_dir in PROJECTS_DIR.iterdir():
        if not data_proj_dir.is_dir():
            continue
            
        proj_name = data_proj_dir.name
        logic_dir = HOME / proj_name
        
        if proj_name == "agentmanager":
            logic_dir = Path("/home/ubuntu/agentmanager")
            
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
