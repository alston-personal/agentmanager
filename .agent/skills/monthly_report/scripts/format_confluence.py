#!/usr/bin/env python3
"""
Monthly Report - Confluence Formatter
Aggregates node slices and formats the content strictly into the DQA Confluence template.
"""
import json
import sys
from date_calculator import get_report_metadata


def format_confluence_report(slices: list[dict], year: int, month: int, reporter: str = "alston.huang") -> dict:
    meta = get_report_metadata(year, month, reporter)
    
    # 1. Extract and aggregate recent week items (for 本週工作重點)
    week_bullets = []
    seen_week_keys = set()
    
    # Group by category
    categories_week = {}
    for sl in slices:
        for it in sl.get("recent_week_items", []):
            cat = it.get("category", "核心業務")
            item = it.get("item", "")
            if item in seen_week_keys:
                continue
            seen_week_keys.add(item)
            categories_week.setdefault(cat, []).append(item)
            
    # Format 本週工作重點
    for cat, items in categories_week.items():
        week_bullets.append(f"- {cat}")
        for it in items:
            week_bullets.append(f"  - {it}")
            
    # 2. Extract and aggregate all monthly records (for 進度與狀態記錄)
    categories_month = {}
    seen_month_keys = set()
    for sl in slices:
        for it in sl.get("monthly_records", []):
            cat = it.get("category", "核心業務")
            item = it.get("item", "")
            status = it.get("status", "proceeding")
            details = it.get("details", [])
            key = f"{cat}:{item}"
            if key in seen_month_keys:
                continue
            seen_month_keys.add(key)
            categories_month.setdefault(cat, []).append({
                "item": item,
                "status": status,
                "details": details
            })
            
    month_bullets = []
    for cat, items in categories_month.items():
        # Determine overall category status if possible, or print per-item
        month_bullets.append(f"- {cat}")
        for it in items:
            st = it["status"]
            month_bullets.append(f"  - {it['item']} - {st}")
            for d in it["details"]:
                month_bullets.append(f"    - {d}")
                
    markdown_body = f"""## 每週工作計畫與狀態

### 本週工作重點
{chr(10).join(week_bullets)}

### 進度與狀態記錄
{chr(10).join(month_bullets)}
"""

    return {
        "metadata": meta,
        "confluence_markdown": markdown_body.strip()
    }


if __name__ == "__main__":
    from collect_node_slice import collect_node_work
    now = datetime = __import__("datetime").datetime.now()
    y = int(sys.argv[1]) if len(sys.argv) > 1 else now.year
    m = int(sys.argv[2]) if len(sys.argv) > 2 else now.month
    
    # Collect slice from local node as demo
    node_slice = collect_node_work("dqa03backup", y, m)
    result = format_confluence_report([node_slice], y, m)
    
    print(f"Page Title: {result['metadata']['page_title']}")
    print(f"Date: {result['metadata']['report_date_table']}")
    print(f"Reporter: @{result['metadata']['reporter']}")
    print("-" * 40)
    print(result["confluence_markdown"])
