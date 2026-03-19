#!/usr/bin/env python3
import os
import sys
import shutil

PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
IDEAS_DIR = os.path.join(PROJECT_ROOT, "ideas")
SPECS_DIR = os.path.join(PROJECT_ROOT, "specs")

def main():
    if len(sys.argv) < 2:
        print("❌ Usage: python3 idea_to_spec.py [idea_slug]")
        return

    slug = sys.argv[1].replace(".md", "")
    idea_path = os.path.join(IDEAS_DIR, f"{slug}.md")
    spec_path = os.path.join(SPECS_DIR, f"{slug}.md")

    if not os.path.exists(idea_path):
        print(f"❌ Error: Idea file not found @ {idea_path}")
        return

    print(f"🔍 Moving '{slug}' from Ideation to Analytics...")
    
    # 讀取原本內容
    with open(idea_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 轉化為 Spec 模板
    spec_content = f"""# 🔍 System Analysis: {slug}

## 📍 Original Idea Context
> [!NOTE]
> This requirement evolved from an initial brainstorm.

{content}

---

## 🏗️ Technical Specification (Analytic Focus)
*Apply `CORE_ANALYTIC.md` rules to fill the following:*

### 1. Functional Requirements
- Requirement A
- Requirement B

### 2. Technical Feasibility
- [ ] Logic/Data compatibility
- [ ] Tool/Skill availability

### 3. Edge Cases & Risks
- Risk A
- Mitigation B

## ✅ User Confirmation
- [ ] User has approved this specification.
"""

    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec_content)

    # 刪除舊檔案
    os.remove(idea_path)
    print(f"✅ Success! Moved to: {spec_path}. Switching to Analytic persona.")

if __name__ == "__main__":
    main()
