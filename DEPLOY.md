# 部署到 PythonAnywhere

以下指令中的 `<帳號>` 請換成你的 PythonAnywhere 使用者名稱，網站網址會是 `https://<帳號>.pythonanywhere.com`。

> ✅ 本文件已在 2026/10/26 實際部署驗證過：帳號 `Asher`，網址 https://asher.pythonanywhere.com，Python 3.13。
> Gmail 寄信也已確認可用：免費方案可以連到 Gmail，忘記密碼信能寄到並重設密碼。

## 目前的部署

| 項目 | 值 |
|---|---|
| 網址 | https://asher.pythonanywhere.com |
| 程式碼 | `/home/Asher/timetable` |
| 虛擬環境 | `/home/Asher/.virtualenvs/timetable-venv`（Python 3.13） |
| WSGI 設定檔 | `/var/www/asher_pythonanywhere_com_wsgi.py`（原始檔備份在 `~/wsgi_backup.py`） |
| 停用日 | 2026/11/26（每月要延長一次，見第 7 節） |

## 0. 事前確認

- **Python 版本**：本專案使用 Django 6.1，需要 **Python 3.12 以上**。PythonAnywhere 目前可選 3.7～3.13，請選 **3.13**。
- **網域大小寫**：後台顯示的網域是 `Asher.pythonanywhere.com`（保留帳號大小寫），但瀏覽器和檔名都會轉成小寫 `asher`，兩者都能用。
- **GitHub repo 公開或私人**：私人 repo 在 `git clone` 時需要登入，建議改用 GitHub 的 Personal Access Token。

## 1. 下載程式碼並安裝套件

到 PythonAnywhere 的 **Consoles** 頁面開一個 **Bash** console，依序執行：

```bash
git clone https://github.com/11446006-Asher-Yu/timetable.git
cd timetable
mkvirtualenv --python=python3.13 timetable-venv   # 版本號要和第 4 步網站選的一樣
pip install -r requirements.txt
```

`pip install` 在免費方案大約要 1 分鐘，期間畫面可能沒有輸出，等提示字元重新出現即可。

`mkvirtualenv` 完成後，提示字元前面會出現 `(timetable-venv)`。之後重開 console 要先執行 `workon timetable-venv`。

## 2. 建立 .env（機密設定，不會上傳 GitHub）

用下面這行指令直接產生 `.env`。金鑰由伺服器隨機產生並寫進檔案，**不會顯示在畫面上**，也不會沿用本機那組。`<帳號>` 請換成小寫的帳號名稱：

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; open('.env','w').write('DJANGO_SECRET_KEY='+g()+'\nDJANGO_DEBUG=False\nDJANGO_ALLOWED_HOSTS=<帳號>.pythonanywhere.com\nEMAIL_HOST_USER=\nEMAIL_HOST_PASSWORD=\n')" && chmod 600 .env && grep -v SECRET .env
```

最後的 `grep` 只會列出金鑰以外的設定，方便確認內容。

### 設定寄信（忘記密碼用）

1. 準備寄件用的 Gmail 帳號（建議另外申請），在 Google 帳戶開啟**兩步驟驗證**。
2. 到 `https://myaccount.google.com/apppasswords` 產生「應用程式密碼」（16 個字母，只顯示一次）。
3. `nano ~/timetable/.env`，填入下面兩行（等號前後不加空格、不加引號，密碼**拿掉空格**）。存檔：`Ctrl+O` → `Enter` → `Ctrl+X`。
   ```
   EMAIL_HOST_USER=寄件用的Gmail地址
   EMAIL_HOST_PASSWORD=16碼應用程式密碼
   ```
4. 先在 console 寄一封測試信，印出 `1` 就是成功（收件地址要加引號、放在中括號裡）：
   ```bash
   cd ~/timetable && workon timetable-venv && python manage.py shell -c "from django.core.mail import send_mail; print(send_mail('課表網站測試信', '寄信設定成功！', None, ['收件信箱']))"
   ```
5. **到 Web 頁面按 Reload。** 網站只在重新載入時讀取 `.env`；沒按的話，console 測試信寄得出去，但網站的忘記密碼信不會寄出。

| 錯誤訊息包含 | 可能原因 |
|---|---|
| `Username and Password not accepted` | 帳號打錯、密碼留著空格，或填了 Gmail 登入密碼而非應用程式密碼 |
| `NameError: name '...' is not defined` | 測試指令的收件地址少了引號 |
| 測試信成功、網站的信沒寄出 | 改完 `.env` 沒按 Reload |

## 3. 建立資料庫、匯入節次、整理靜態檔

```bash
python manage.py migrate
python manage.py loaddata periods
python manage.py collectstatic --noinput
python manage.py createsuperuser   # 建立後台管理員，密碼自己設定
```

## 4. 設定網站（Web 頁面）

1. 到 **Web** 頁面，按 **Add a new web app**。
2. 免費帳號不能自訂網域，直接按 **Next**，網域會是 `<帳號>.pythonanywhere.com`。
3. 框架選 **Manual configuration (including virtualenvs)**（不要選「Django」，那個選項會另外建一個新專案）。
4. Python 版本選 **3.13**（和第 1 步 `mkvirtualenv` 相同），再按 **Next** 完成建立。
5. 建立完成後，在 Web 頁面設定以下項目。每個欄位都是**點一下文字才會出現輸入框**，填好按 Enter 或打勾鈕儲存：

| 區塊 | 欄位 | 填入 |
|---|---|---|
| Code | Source code | `/home/<帳號>/timetable` |
| Code | Working directory | `/home/<帳號>/timetable` |
| Virtualenv | 路徑 | `/home/<帳號>/.virtualenvs/timetable-venv` |
| Static files | URL：`/static/` | Directory：`/home/<帳號>/timetable/staticfiles` |
| Security | Force HTTPS | Enabled（開啟後 http 會自動轉到 https） |

6. 改寫 WSGI 設定檔（檔名是 `/var/www/<小寫帳號>_pythonanywhere_com_wsgi.py`）。可以點 **Code** 區塊裡的 **WSGI configuration file** 連結用網頁編輯器改，**把內容全部刪掉**，換成下面的內容。也可以在 Bash console 先備份再覆寫：`cp /var/www/<小寫帳號>_pythonanywhere_com_wsgi.py ~/wsgi_backup.py`。

```python
import os
import sys

path = '/home/<帳號>/timetable'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

存檔後回到 Web 頁面，按最上方綠色的 **Reload** 按鈕。

## 5. 上線後檢查

- [ ] 開啟 `https://<帳號>.pythonanywhere.com`，首頁有正常的樣式（樣式跑掉代表第 4 步的 Static files 沒設好）
- [ ] 註冊、登入、登出
- [ ] 新增、修改、刪除課程，課表格子顯示正確
- [ ] 「上課中」標示時間正確
- [ ] 手機開啟，畫面是星期分頁
- [ ] 匯出圖片、列印
- [x] 開啟分享，用無痕視窗開分享連結；**分享網址開頭要是 `https://`**（2026/10/26 已確認）
- [x] 忘記密碼：收到重設密碼信，也能設定新密碼（2026/10/26 已確認）
  - `.env` 的 `EMAIL_HOST_USER` 留白，或改了 `.env` 卻沒按 Reload 時，**不會真的寄信**，信件只會寫進 `/var/log/<帳號>.pythonanywhere.com.server.log`，畫面仍會顯示「請查收信件」。
- [ ] `https://<帳號>.pythonanywhere.com/admin/` 能用管理員帳號登入

2026/10/26 部署後已確認：首頁樣式正常、http 自動轉 https、登入／註冊／忘記密碼頁正常、未登入開課表會轉到登入頁、不存在的分享連結顯示中文 404、後台登入頁正常。

出現錯誤時，到 Web 頁面最下方的 **Log files** 看 **Error log**。

## 6. 之後更新網站

本機改完並推送到 GitHub 後，在 PythonAnywhere 的 Bash console 執行：

```bash
workon timetable-venv
cd ~/timetable
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

最後回到 Web 頁面按 **Reload**。

## 7. 免費方案注意事項

- **每個月要延長一次**：至少每個月登入一次，到 Web 頁面按「**Run until 1 month from today**」，否則網站會停用。停用前一週 PythonAnywhere 會寄信提醒。目前停用日是 **2026/11/26**，**老師評分前記得確認還沒到期。**
- 免費方案對外連線有限制，但連到 Gmail（smtp.gmail.com）寄信實測可用。
- 改過伺服器上的 `.env` 後，一定要到 Web 頁面按 **Reload** 才會生效。
- 檔案空間上限 512 MB，CPU 每天 100 秒；本專案只用到很小一部分。
