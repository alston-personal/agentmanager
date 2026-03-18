# 歷史成形器 - 立即行動指南

> 從想法到 POC 的具體步驟

---

## 🎯 目標

在 **2 週內** 完成可展示的 POC,驗證:
1. 技術可行性 (AI 能準確抽取事件嗎?)
2. 商業價值 (企業願意付費嗎?)
3. 用戶體驗 (操作簡單嗎?)

---

## 🚀 立即開始的 3 個步驟

### 1️⃣ 現在就做 (5 分鐘)
- 申請 SerpAPI 免費帳號: https://serpapi.com/users/sign_up
- 取得 API key

### 2️⃣ 今天完成 (30 分鐘)
- 建立 Supabase 專案: "history-synthesizer-poc"
- 執行 SQL 建立資料表 (見下方)
- 測試連線

### 3️⃣ 本週完成 (2-3 小時)
- 在 n8n 建立第一個 Workflow
- 測試新聞爬取
- 看到第一個結果!

---

## 📋 Supabase 資料表設定

```sql
CREATE TABLE company_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name TEXT NOT NULL,
  event_date DATE,
  date_precision TEXT,
  description TEXT NOT NULL,
  people JSONB,
  event_type TEXT,
  confidence INTEGER,
  source_url TEXT,
  source_title TEXT,
  source_type TEXT,
  raw_content TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_company_name ON company_events(company_name);
CREATE INDEX idx_event_date ON company_events(event_date);
CREATE INDEX idx_confidence ON company_events(confidence DESC);
```

---

## 🔧 n8n Workflow 節點配置

### Gemini 事件抽取 Prompt

**System:**
```
你是企業歷史事件抽取專家。從新聞內容中抽取:
1. event_date: 事件日期 (YYYY-MM-DD)
2. date_precision: 'day', 'month', 或 'year'
3. description: 事件描述 (一句話)
4. people: [{"name": "...", "role": "..."}]
5. event_type: 'product_launch', 'executive_change', 'financial', 'acquisition', 'other'
6. confidence: 0-100

只輸出 JSON。
```

**User:**
```
新聞標題: {{ $json.title }}
新聞內容: {{ $json.content }}
```

---

## 📅 2 週時間表

**Week 1**: 環境設定 + 第一個 Workflow + 測試
**Week 2**: 多來源整合 + 視覺化 + 完整測試

---

## 💰 預算

- SerpAPI: $0-50/月
- Gemini: $0-20 (Flash 方案有很大免費額度)
- Supabase: $0 (免費)
**總計**: < $100

---

## 🎯 2 週後你會有

- ✅ 自動爬取新聞的 Workflow
- ✅ 50+ 個事件的資料庫
- ✅ 互動式時間軸展示
- ✅ 3 家公司的完整歷史

**然後決定是否繼續開發!** 🚀
