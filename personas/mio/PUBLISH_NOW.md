# 澪｜圖文發佈即時操作卡（跨對話／跨 Agent）

**任務觸發：** 使用者要求澪在 Threads 發文、發圖片、繼續發文，或懷疑功能又失效時，第一時間讀本檔和 `personas/mio/THREADS_RUNBOOK.md`。這是操作索引，不是新的發文實作。

**禁止:** 未實際探測就聲稱「沒有工具／在另一個對話」；要求使用者再上傳同一張原圖／手動 GitHub 上傳；擅自重複使用舊插畫、未授權圖片或未核准的新文案；把 GitHub Commit / Actions 啟動當成 Threads 發佈成功；把未知結果的貼文重新送出造成重複。

## 先發現工具，不能憑印象判定能力

- 使用當回合已連結的 GitHub 工具，必要時透過 `ALL_TOOLS` 搜尋 `mcp__GitHub__fetch_file/create_blob/create_tree/create_commit/update_ref/create_file/fetch_workflow_run_jobs/fetch_workflow_job_logs`。實際使用目前工具參數 schema，不得假定上次的工具還在，也不能不查就說它不在。
- 讀 `alston-personal/agentmanager` 的 `core/integration` 分支和 `.github/workflows/oracle-publish-mio-approved.yml`、`scripts/publish_galaxy_threads_day1_user.sh`；這個 repo 的本檔／runbook 保存已成功的傳輸方式。
- 檔案輸入直接使用本對話原始附件可用的 container 路徑；先確認圖片 bytes、尺寸、版權／使用者核准及是否已發過，不擅自改生成人物或圖文。
- GitHub `create_file` **只接受 UTF-8 文字**。圖片先以原始 bytes base64 傳給 `create_blob(encoding="base64")`。如果 container 與 connector 隔離，將完整 base64 暫存文字檔 → Files Library upload → Files.read(full) → GitHub.create_blob；處理完刪暫存。**任何讀取不完整就停止，不以貼文文字代替圖片。**

## 單張圖文：已在真實 Threads 通過

1. 新的 `personas/mio/approved/assets/<unique-file>.jpg|png` → GitHub 圖片 blob/tree，確認 SHA/原圖、公開 URL 可讀。
2. 新的 `personas/mio/approved/mio-post-<unique-post-key>.json`：`image_path`, `image_alt_text`。圖片和 manifest **先上傳／提交**，不會觸發發文。
3. **最後**新增一個 `personas/mio/approved/mio-post-<unique-post-key>.txt`（使用者核准的文案）到 `core/integration`，會觸發 GitHub Actions。切勿一個 commit 新增多個觸發 .txt。
4. 經 GitHub `fetch` 查 `https://api.github.com/repos/alston-personal/agentmanager/actions/runs?head_sha=<trigger-commit>`，接著 `fetch_workflow_run_jobs` → `fetch_workflow_job_logs`；需要 `mio_approved_receipt=PASS`、`galaxy_day1_publish=PASS`（或已存在且同一貼文驗證）、`galaxy_day1_image_asset=VERIFIED`、`galaxy_day1_image_readback=PASS`、新貼文 ID 和 permalink 才回報成功。若 Actions 顯示失敗先查平台 ID，**禁止盲目重發**。
5. 已驗證範例：[兩張料理合成圖已發文 run 35507932838](https://github.com/alston-personal/agentmanager/actions/runs/35507932838)，Threads ID `18102186647629092`，https://www.threads.com/@mio.milkcat/post/DdgerB_FL5P 。這是 **ONE IMAGE 的合成圖，不是可左右滑動多圖**，不得再拿它當新的公開測試素材。

## 多圖現況與啟用界線

- 線上正式發文流程目前只有 `image_path + image_alt_text` 單圖。多張原圖應以 Meta 官方 `CAROUSEL` 父容器來發，**不是重複單圖、不是合成一張**。正式功能實測通過前不得聲稱已可發多圖，亦不可用使用者已有公開貼文做測試而造成重複。
- 多圖新版放在獨立功能分支／PR 驗證，需支援 manifest `images: [{image_path,image_alt_text}, ...]`（2–20 張），每張圖片 CDN digest 驗證，建立 `is_carousel_item=true` 私有子容器、等待完成、建立唯一 CAROUSEL 母容器並只發佈一次；真實回讀需檢查貼文 ID、CAROUSEL 類型及子圖數量。
- 禁止用無法確認的模型輸出或已刪除的貼文當作「功能驗收成功」。每次上線改動只驗證合約/容器，不自動發公開測試貼文。要正式驗收公開貼文，先用使用者當次已核准、**尚未發過**的素材。
