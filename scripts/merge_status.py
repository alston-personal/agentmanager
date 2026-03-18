import re
import sys
import os

def merge_md(path_legacy, path_new, path_output):
    content_legacy = open(path_legacy).read() if os.path.exists(path_legacy) else ""
    content_new = open(path_new).read() if os.path.exists(path_new) else ""
    
    # 提取 Log
    log_pattern = re.compile(r'<!-- LOG_START -->(.*?)<!-- LOG_END -->', re.DOTALL)
    new_logs = log_pattern.search(content_new).group(1).strip() if log_pattern.search(content_new) else ""
    old_logs = log_pattern.search(content_legacy).group(1).strip() if log_pattern.search(content_legacy) else ""
    
    # 合併日誌，過濾掉重複的且讓新日誌居首
    all_logs = []
    if new_logs: all_logs.append(new_logs)
    if old_logs: all_logs.append(old_logs)
    merged_logs = "\n".join(all_logs)
    
    # 使用舊的 Summary 當作基底 (資訊多)，更新日期
    merged_content = log_pattern.sub(f"<!-- LOG_START -->\n{merged_logs}\n<!-- LOG_END -->", content_legacy if content_legacy else content_new)
    # 更新日期為最新日期
    merged_content = re.sub(r'\|\s*\*\*Last Updated\*\*\s*\|.*\|', f"| **Last Updated** | 2026-03-16 |", merged_content)
    
    with open(path_output, 'w') as f:
        f.write(merged_content)

# 針對 Zeus Writer 同步
merge_md("/tmp/zeus_legacy.md", "/home/ubuntu/agent-data/projects/zeus-writer/STATUS.md", "/home/ubuntu/agent-data/projects/zeus-writer/STATUS.md")
