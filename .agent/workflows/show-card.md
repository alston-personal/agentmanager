---
description: 展示石虎塔羅牌的成品圖檔與詳細內容
---
// turbo-all

# /show-card [牌名或序號] - 即時展示石虎塔羅牌

## 🎯 目的
快速檢索並呈現 `leopardcat-tarot` 專案中已生成的卡片成品、優化後的提示詞以及生態意涵。

## Steps

1. **解析輸入並定位文件**
   這個步驟會根據輸入（如 "0", "愚人", "the fool"）來尋找對應的 JSON。
   ```bash
   QUERY="{{card_query}}"
   # 簡單轉換邏輯（此處由 Agent 執行時自動匹配文件）
   ```

2. **讀取 JSON 並提取圖檔路徑**
   讀取 `leopardcat-tarot/generator/cards/` 下的對應文件，提取 `main_image` 欄位。

3. **呈現卡片詳情**
   使用 Carousel 呈現：
   - 第一張：卡片主視覺 (Main Art)
   - 第二張：生態意涵與牌義 (Meaning & Ecology)
   - 第三張：生圖技術參數 (Prompt Architecture)

---

## 使用範例
- `/show-card 0`
- `/show-card 愚人`
- `/show-card the magician`
