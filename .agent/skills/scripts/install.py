#!/usr/bin/env python3
"""
Skills 安裝腳本（跨平台）
用途：在新的 workspace 快速部署共享的 skills

使用方法：
    python install.py
    python install.py --from-git
    python install.py --source /path/to/local/skills
"""

import os
import sys
import argparse
import shutil
import subprocess
import platform
from pathlib import Path
from datetime import datetime


class Colors:
    """跨平台的顏色輸出"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

    @staticmethod
    def colored(text, color):
        """如果終端支援，返回有顏色的文字"""
        if sys.stdout.isatty():
            return f"{color}{text}{Colors.END}"
        return text


def print_header(text):
    """列印標題"""
    print()
    print(Colors.colored("=" * 60, Colors.CYAN))
    print(Colors.colored(f"  {text}", Colors.CYAN))
    print(Colors.colored("=" * 60, Colors.CYAN))
    print()


def print_success(text):
    print(Colors.colored(f"✅ {text}", Colors.GREEN))


def print_error(text):
    print(Colors.colored(f"❌ {text}", Colors.RED))


def print_warning(text):
    print(Colors.colored(f"⚠️  {text}", Colors.YELLOW))


def print_info(text):
    print(Colors.colored(f"ℹ️  {text}", Colors.BLUE))


def run_command(cmd, cwd=None):
    """執行命令並返回結果"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=False
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def check_git_installed():
    """檢查 Git 是否已安裝"""
    success, _, _ = run_command(["git", "--version"])
    return success


def install_from_git(target_path, repo_url):
    """從 Git 倉庫安裝 skills"""
    print_info(f"從 Git 倉庫安裝: {repo_url}")
    
    if target_path.exists():
        if (target_path / ".git").exists():
            # 已經是 Git 倉庫，執行 pull
            print_info("檢測到已存在的 Git 倉庫，執行更新...")
            success, stdout, stderr = run_command(["git", "pull"], cwd=target_path)
            if success:
                print_success("Skills 已更新到最新版本")
                return True
            else:
                print_error(f"更新失敗: {stderr}")
                return False
        else:
            print_warning(f"目標路徑已存在但不是 Git 倉庫: {target_path}")
            response = input("是否要備份並重新安裝？(y/N): ").strip().lower()
            if response != 'y':
                print_error("安裝已取消")
                return False
            
            # 備份
            backup_path = f"{target_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print_info(f"備份到: {backup_path}")
            shutil.move(str(target_path), backup_path)
    
    # 執行 clone
    target_path.parent.mkdir(parents=True, exist_ok=True)
    success, stdout, stderr = run_command(["git", "clone", repo_url, str(target_path)])
    
    if success:
        print_success("Skills 已成功安裝")
        return True
    else:
        print_error(f"安裝失敗: {stderr}")
        return False


def install_from_local(source_path, target_path):
    """從本地路徑複製 skills"""
    print_info(f"從本地複製: {source_path}")
    
    if not source_path.exists():
        print_error(f"來源路徑不存在: {source_path}")
        return False
    
    if target_path.exists():
        print_warning(f"目標路徑已存在: {target_path}")
        response = input("是否要覆蓋？(y/N): ").strip().lower()
        if response != 'y':
            print_error("安裝已取消")
            return False
        
        # 備份
        backup_path = f"{target_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print_info(f"備份到: {backup_path}")
        shutil.move(str(target_path), backup_path)
    
    # 複製
    try:
        shutil.copytree(source_path, target_path)
        print_success("Skills 已成功複製")
        return True
    except Exception as e:
        print_error(f"複製失敗: {e}")
        return False


def list_installed_skills(skills_path):
    """列出已安裝的 skills"""
    if not skills_path.exists():
        print_warning("Skills 目錄不存在")
        return
    
    print()
    print_info("已安裝的 Skills:")
    
    skills_found = False
    for item in skills_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skills_found = True
                # 讀取 skill 描述
                try:
                    with open(skill_md, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # 簡單解析 YAML frontmatter
                        if content.startswith('---'):
                            lines = content.split('\n')
                            name = desc = ""
                            for line in lines[1:]:
                                if line.strip() == '---':
                                    break
                                if line.startswith('name:'):
                                    name = line.split(':', 1)[1].strip()
                                if line.startswith('description:'):
                                    desc = line.split(':', 1)[1].strip()
                            
                            print(Colors.colored(f"  ✓ {name}", Colors.GREEN))
                            if desc:
                                print(f"    {desc}")
                except Exception:
                    print(Colors.colored(f"  ⚠ {item.name}", Colors.YELLOW))
    
    if not skills_found:
        print_warning("未找到任何 skills")
    print()


def detect_workspace_root():
    """自動檢測 workspace 根目錄"""
    current = Path.cwd()
    
    # 向上尋找包含 .agent 目錄的路徑
    while current != current.parent:
        if (current / ".agent").exists():
            return current
        current = current.parent
    
    # 找不到，返回當前目錄
    return Path.cwd()


def main():
    parser = argparse.ArgumentParser(
        description="Skills 安裝工具（跨平台）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  # 從 Git 安裝
  python install.py --from-git
  
  # 從本地路徑安裝
  python install.py --source /path/to/skills
  
  # 指定目標路徑
  python install.py --from-git --target /custom/path
  
  # 列出已安裝的 skills
  python install.py --list
        """
    )
    
    parser.add_argument(
        '--from-git',
        action='store_true',
        help='從 Git 倉庫安裝'
    )
    parser.add_argument(
        '--repo',
        default='https://github.com/alstonhuang/shared-agent-skills.git',
        help='Git 倉庫 URL（預設：alstonhuang/shared-agent-skills）'
    )
    parser.add_argument(
        '--source',
        help='本地 skills 來源路徑'
    )
    parser.add_argument(
        '--target',
        help='安裝目標路徑（預設：.agent/skills）'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出已安裝的 skills'
    )
    
    args = parser.parse_args()
    
    # 檢測 workspace 根目錄
    workspace_root = detect_workspace_root()
    
    # 確定目標路徑
    if args.target:
        target_path = Path(args.target)
    else:
        target_path = workspace_root / ".agent" / "skills"
    
    print_header("Skills 安裝工具")
    print(f"作業系統: {platform.system()} {platform.release()}")
    print(f"Python 版本: {platform.python_version()}")
    print(f"Workspace 根目錄: {workspace_root}")
    print(f"目標路徑: {target_path}")
    
    # 列出已安裝的 skills
    if args.list:
        list_installed_skills(target_path)
        return 0
    
    # 檢查 Git
    if args.from_git and not check_git_installed():
        print_error("Git 未安裝或不在 PATH 中")
        print_info("請安裝 Git: https://git-scm.com/downloads")
        return 1
    
    # 執行安裝
    success = False
    
    if args.from_git:
        # 從 Git 安裝
        success = install_from_git(target_path, args.repo)
    elif args.source:
        # 從本地安裝
        source_path = Path(args.source)
        success = install_from_local(source_path, target_path)
    else:
        # 預設：嘗試從預設本地路徑複製
        default_source = Path(__file__).parent.parent
        if default_source.exists():
            print_info("使用預設本地來源")
            success = install_from_local(default_source, target_path)
        else:
            print_error("請指定 --from-git 或 --source")
            parser.print_help()
            return 1
    
    if success:
        # 列出已安裝的 skills
        list_installed_skills(target_path)
        
        print_header("安裝完成")
        print_success("Skills 已成功安裝！")
        print()
        print_info("下一步：")
        print("  1. 重新啟動 Antigravity 以載入新的 skills")
        print("  2. 查看 SKILL.md 了解每個 skill 的使用方法")
        print()
        
        if args.from_git:
            print_info("更新 skills 的方法：")
            print(f"  cd {target_path}")
            print("  git pull")
            print()
        
        return 0
    else:
        print_error("安裝失敗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
