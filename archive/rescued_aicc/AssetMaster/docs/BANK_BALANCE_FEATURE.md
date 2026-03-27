# 銀行餘額追蹤功能說明

## 📋 功能概述

AssetMaster 現在支援完整的銀行餘額追蹤功能，讓您可以記錄和管理多種貨幣的現金帳戶，包括：

### 支援的貨幣類型

#### 法定貨幣 (FIAT)
- 💵 **台幣 (TWD)** - 台灣新台幣
- 💵 **美元 (USD)** - 美金
- 💵 **日圓 (JPY)** - 日幣

#### 加密貨幣 (CRYPTO)
- ₿ **USDT** - Tether 穩定幣
- ₿ **BTC** - 比特幣
- ₿ **ETH** - 以太坊
- ₿ **BNB** - 幣安幣

## 🎯 主要功能

### 1. 新增帳戶
- 點擊「新增帳戶」按鈕
- 填寫帳戶資訊：
  - **帳戶名稱** (必填)：例如「台新銀行台幣帳戶」
  - **帳戶類型** (必填)：法定貨幣或加密貨幣
  - **幣別** (必填)：根據帳戶類型選擇對應幣別
  - **餘額** (必填)：當前帳戶餘額
  - **金融機構** (選填)：例如「台新銀行」、「Binance」
  - **備註** (選填)：其他說明

### 2. 編輯帳戶
- 點擊帳戶卡片上的編輯圖示 (✏️)
- 可以更新帳戶名稱、餘額、金融機構和備註
- **注意**：帳戶類型和幣別在創建後無法修改

### 3. 刪除帳戶
- 點擊帳戶卡片上的刪除圖示 (🗑️)
- 確認後將軟刪除該帳戶（設為不活躍狀態）

### 4. 分類顯示
- **法定貨幣帳戶**：顯示所有 TWD、USD、JPY 帳戶
- **加密貨幣帳戶**：顯示所有 USDT、BTC、ETH、BNB 等帳戶

## 🏗️ 技術實作

### 資料庫架構
新增 `BankAccount` 資料表，包含以下欄位：
```prisma
model BankAccount {
  id          String   @id @default(uuid())
  accountName String   // 帳戶名稱
  accountType String   // FIAT, CRYPTO
  currency    String   // TWD, USD, JPY, USDT, BTC, ETH, etc.
  balance     Float    @default(0.0)
  institution String?  // 金融機構
  notes       String?  // 備註
  isActive    Boolean  @default(true)
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}
```

### API 端點
- **GET** `/api/bank-accounts` - 取得所有活躍帳戶
- **POST** `/api/bank-accounts` - 新增帳戶
- **PATCH** `/api/bank-accounts` - 更新帳戶
- **DELETE** `/api/bank-accounts?id={id}` - 軟刪除帳戶

### UI 組件
- `BankAccounts.tsx` - 主要管理介面
  - 帳戶列表顯示
  - 新增/編輯模態框
  - CRUD 操作處理

### 整合到儀表板
- 在主頁面 (`page.tsx`) 新增銀行帳戶區塊
- 與其他數據一起自動刷新
- 使用相同的設計系統（Glassmorphism 風格）

## 🎨 UI/UX 特色

1. **分類清晰**：法定貨幣和加密貨幣分開顯示
2. **視覺圖示**：
   - 🏦 法定貨幣帳戶使用建築圖示
   - ₿ 加密貨幣帳戶使用比特幣圖示
3. **響應式設計**：支援手機、平板、桌面
4. **即時更新**：新增/編輯/刪除後立即刷新
5. **優雅的模態框**：使用 Glassmorphism 設計風格

## 📝 使用範例

### 範例 1: 新增台幣帳戶
```
帳戶名稱: 台新銀行台幣帳戶
帳戶類型: 法定貨幣
幣別: TWD
餘額: 500000
金融機構: 台新銀行
備註: 主要儲蓄帳戶
```

### 範例 2: 新增加密貨幣帳戶
```
帳戶名稱: Binance USDT 錢包
帳戶類型: 加密貨幣
幣別: USDT
餘額: 10000
金融機構: Binance
備註: 用於交易的穩定幣
```

## 🔄 未來擴展方向

1. **自動同步**：整合銀行 API 自動更新餘額
2. **匯率轉換**：顯示所有帳戶的等值基準貨幣總額
3. **歷史記錄**：追蹤餘額變化歷史
4. **圖表視覺化**：顯示現金配置比例
5. **交易關聯**：與 Ledger 交易記錄整合

## 🚀 如何使用

1. 啟動開發伺服器：
   ```bash
   npm run dev
   ```

2. 開啟瀏覽器訪問 `http://localhost:3000`

3. 在主儀表板底部找到「銀行餘額」區塊

4. 點擊「新增帳戶」開始管理您的現金帳戶

---

**最後更新**: 2026-01-30
**版本**: 1.0.0
