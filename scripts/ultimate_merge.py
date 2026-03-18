import re
import os
import shutil

DATA_PATH = "/home/ubuntu/agent-data/projects"

def get_logs(content):
    log_pattern = re.compile(r'<!-- LOG_START -->(.*?)<!-- LOG_END -->', re.DOTALL)
    match = log_pattern.search(content)
    return match.group(1).strip() if match else ""

def merge_project(legacy_p, modern_p):
    legacy_file = os.path.join(DATA_PATH, legacy_p, "STATUS.md")
    modern_file = os.path.join(DATA_PATH, modern_p, "STATUS.md")
    
    if os.path.exists(legacy_file) and os.path.exists(modern_file):
        print(f"Merging {legacy_p} -> {modern_p}...")
        l_content = open(legacy_file).read()
        m_content = open(modern_file).read()
        
        l_logs = get_logs(l_content)
        m_logs = get_logs(m_content)
        
        # 合併 Logs
        combined_logs = "\n".join(filter(None, [m_logs, l_logs]))
        
        # 以 Legacy 做基底 (歷史訊息較多)，但使用新專案名稱
        # 取 Legacy 的 Summary、Todo、Roadmap
        final_content = re.sub(r'# Project Status:.*', f"# Project Status: {modern_p}", l_content)
        final_content = re.sub(r'<!-- LOG_START -->.*?<!-- LOG_END -->', 
                               f"<!-- LOG_START -->\n{combined_logs}\n<!-- LOG_END -->", 
                               final_content, flags=re.DOTALL)
        
        # 更新最後日期
        final_content = re.sub(r'\|\s*\*\*Last Updated\*\*\s*\|.*\|', 
                               f"| **Last Updated** | 2026-03-16 |", final_content)
        
        # 寫回新檔案
        with open(modern_file, 'w') as f:
            f.write(final_content)
        
        # 搬移 Memory (如果有遺漏)
        legacy_mem = os.path.join(DATA_PATH, legacy_p, "memory")
        modern_mem = os.path.join(DATA_PATH, modern_p, "memory")
        if os.path.exists(legacy_mem):
            if not os.path.exists(modern_mem): os.makedirs(modern_mem)
            for f in os.listdir(legacy_mem):
                shutil.move(os.path.join(legacy_mem, f), os.path.join(modern_mem, f))
                
        # 刪除舊專案目錄
        shutil.rmtree(os.path.join(DATA_PATH, legacy_p))
        print(f"✅ Successfully merged and removed {legacy_p}.")

# 執行對應合併
merge_project("Beauty-PK", "beauty-pk")
merge_project("Y2Helper", "y2helper")
merge_project("n8n-live", "n8n-automation")
merge_project("AI_Command_Center", "ai-command-center")
