#!/usr/bin/env python3
import json
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---
AGENT_DATA_ROOT = Path("/home/ubuntu/agent-data/projects")

def get_issue_dir(project_name):
    issue_dir = AGENT_DATA_ROOT / project_name / "issues"
    issue_dir.mkdir(parents=True, exist_ok=True)
    return issue_dir

def raise_issue(project, title, description, priority="medium", tags=""):
    issue_dir = get_issue_dir(project)
    issue_id = f"ISSUE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    issue_file = issue_dir / f"{issue_id}.json"
    
    data = {
        "id": issue_id,
        "title": title,
        "description": description,
        "status": "OPEN",
        "priority": priority,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "resolution": ""
    }
    
    with open(issue_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Issue {issue_id} successfully created for project '{project}'.")
    return issue_file

def list_issues(project, status="OPEN"):
    issue_dir = get_issue_dir(project)
    print(f"\n📊 Issue Tracker for '{project}' (Status: {status})")
    print("=" * 60)
    
    issues = []
    if issue_dir.exists():
        for f in issue_dir.glob("*.json"):
            with open(f, 'r', encoding='utf-8') as file:
                try:
                    data = json.load(file)
                    if data.get("status") == status or status == "ALL":
                        issues.append(data)
                except json.JSONDecodeError:
                    pass
    
    if not issues:
        print("No issues found in this category.")
        return

    # Sort by priority and date
    priority_map = {"high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda x: (priority_map.get(x.get("priority", "medium"), 2), x.get("created_at", "")))

    for issue in issues:
        tags = f"[{', '.join(issue.get('tags', []))}]" if issue.get("tags") else ""
        print(f"[{issue['priority'].upper()}] {issue['id']} | {issue['title']} {tags}")
        print(f"  └─ {issue['description'][:100]}...")
    print("=" * 60)

def resolve_issue(project, issue_id, resolution):
    issue_dir = get_issue_dir(project)
    issue_file = issue_dir / f"{issue_id}.json"
    
    if not issue_file.exists():
        print(f"❌ Error: Issue {issue_id} not found.")
        return
        
    with open(issue_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    data["status"] = "RESOLVED"
    data["resolved_at"] = datetime.now(timezone.utc).isoformat()
    data["resolution"] = resolution
    
    with open(issue_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Issue {issue_id} has been marked as RESOLVED.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LCS Swarm Issue Tracker CLI")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")
    
    # Parser for 'raise'
    p_raise = subparsers.add_parser("raise", help="Create a new issue")
    p_raise.add_argument("project", help="Project name (e.g. leopardcat-tarot)")
    p_raise.add_argument("title", help="Issue title")
    p_raise.add_argument("description", help="Detailed description of the issue")
    p_raise.add_argument("--priority", choices=["low", "medium", "high"], default="medium", help="Issue priority")
    p_raise.add_argument("--tags", default="", help="Comma separated tags (e.g. 'bug,rework,creative')")
    
    # Parser for 'list'
    p_list = subparsers.add_parser("list", help="List issues for a project")
    p_list.add_argument("project", help="Project name")
    p_list.add_argument("--status", choices=["OPEN", "RESOLVED", "ALL"], default="OPEN", help="Filter by status")
    
    # Parser for 'resolve'
    p_resolve = subparsers.add_parser("resolve", help="Mark an issue as resolved")
    p_resolve.add_argument("project", help="Project name")
    p_resolve.add_argument("issue_id", help="Target Issue ID")
    p_resolve.add_argument("resolution", help="Summary of how it was resolved")

    args = parser.parse_args()
    
    if args.action == "raise":
        raise_issue(args.project, args.title, args.description, args.priority, args.tags)
    elif args.action == "list":
        list_issues(args.project, args.status)
    elif args.action == "resolve":
        resolve_issue(args.project, args.issue_id, args.resolution)
    else:
        parser.print_help()
