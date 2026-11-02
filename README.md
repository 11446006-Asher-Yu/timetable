# 校園課表系統 Campus Timetable

網頁程式設計個人作業（Django）。學生可以維護自己的課表；延伸功能讓排課人員與老師在線上協調排課，公布後學生一鍵加入課表。

- 線上版：https://asher.pythonanywhere.com
- 介面以英文為主，頁首「中文」按鈕可切換繁體中文

## 現場 Demo：5 個步驟（Windows）

1. **下載程式碼**
   ```bash
   git clone https://github.com/11446006-Asher-Yu/timetable.git
   ```
2. **進入資料夾**
   ```bash
   cd timetable
   ```
3. **一鍵安裝並啟動**（也可以在檔案總管直接雙擊 `run_demo.bat`）
   ```bash
   run_demo.bat
   ```
   會自動：找到 Python 3.10 以上 → 建立虛擬環境 → 安裝套件 → 建立資料庫與示範資料 → 啟動網站。第一次約 1 分鐘（需要網路）。
4. **瀏覽器會自動開啟** http://127.0.0.1:8000/ （沒有自動開啟就手動輸入）
5. **用示範帳號登入**（密碼都是 `demo-pass-2026`）

   | 帳號 | 身分 | 登入後進入 | 可以看的功能 |
   |---|---|---|---|
   | `demo_student` | 學生 | 我的課表 | 個人課表（7 門課，含 1 門正式課程）、課程目錄（名額、候補）、分享 |
   | `demo_scheduler` | 排課人員 | 排課總覽 | 排課看板、調整申請、公布 |
   | `demo_teacher` | 老師（王老師） | 老師首頁 | 可授課時段、我的授課、接受／申請調整 |

停止網站：在黑色視窗按 `Ctrl+C`。想把示範資料恢復原狀：再執行一次 `run_demo.bat`。

> 需要 Python 3.10 以上（https://www.python.org/downloads/ ，安裝時勾選「Add python.exe to PATH」）。
> Python 3.12 以上會使用 Django 6.1；3.10、3.11 會自動改用 Django 5.2。

### 不用批次檔的手動步驟

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

不需要 `.env`：沒有 `.env` 時會自動使用本機開發設定（DEBUG 開啟、寄信只印在終端機）。

## 功能

**個人課表維護（主要功能）**
- 註冊、登入、登出、忘記密碼（寄信重設）
- 新增、修改、刪除課程；一門課可有多個上課時段
- 「星期 × 節次」課表格子，依類別上色，自動計算總學分與各類別小計
- 點課程看詳細資料；標出今天與正在上的課
- 衝堂檢查：時段重疊時提示，確認後才儲存；課表上衝堂課程並排顯示
- 手機版星期分頁（可左右滑動）、列印、匯出 PNG 圖片
- 唯讀分享連結（可停止分享、重新產生連結）

**排課協調（延伸功能）**
- 排課人員：學期／教室／班級／開課管理、排課看板（即時檢查老師、教室、班級衝堂與老師可授課時段）、邀請老師、處理調整申請、公布課表（公布前重新檢查教室容量等規則）
- 老師：接受邀請、填寫可授課時段、接受排課或申請調整
- 學生：從課程目錄一鍵加入正式課程；顯示已加入人數與名額，額滿可加入候補，有空位時依序自動遞補

## 測試

```bash
python manage.py test
```

## 技術

Python、Django、SQLite、HTML／CSS（CSS Grid）、原生 JavaScript、html2canvas（匯出圖片）、Django i18n（英文／繁體中文）。

| 資料夾 | 內容 |
|---|---|
| `schedule/` | 個人課表：課程、時段、節次、分享連結 |
| `scheduling/` | 排課協調：學期、教室、班級、開課、可授課時段、調整申請、邀請 |
| `templates/`、`static/` | 頁面、樣式、JavaScript |
| `locale/` | 繁體中文翻譯 |

## 開發者筆記

### 翻譯

程式碼與模板裡寫英文，中文翻譯在 `locale/zh_Hant/LC_MESSAGES/django.po`。新增或修改介面文字後：

```bash
pip install -r requirements-dev.txt
python scripts/i18n_tools.py extract   # 列出缺少翻譯的字串（標 ✗）
python scripts/i18n_tools.py compile   # 編譯成 django.mo
```

`django.mo` 要一起 commit，伺服器不需要安裝 Babel。

### 部署

部署到 PythonAnywhere 的步驟見 [DEPLOY.md](DEPLOY.md)。
