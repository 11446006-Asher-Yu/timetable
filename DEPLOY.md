# 部署到 PythonAnywhere

以下指令中的 `<帳號>` 請換成你的 PythonAnywhere 使用者名稱，網站網址會是 `https://<帳號>.pythonanywhere.com`。

> ⚠️ 標示「待確認」的項目是撰寫時還沒在 PythonAnywhere 上實際驗證過的，部署時請留意畫面上的實際選項。

## 0. 事前確認

- **Python 版本**：本專案使用 Django 6.1，需要 **Python 3.12 以上**。在 Web 頁面新增網站時，請確認可以選到 3.12 以上的版本。
  - 如果最高只有 3.11 以下，**先不要繼續**：要改用 Django 5.2，寄信設定也要跟著改。
- **GitHub repo 公開或私人**：私人 repo 在 `git clone` 時需要登入，建議改用 GitHub 的 Personal Access Token。

## 1. 下載程式碼並安裝套件

到 PythonAnywhere 的 **Consoles** 頁面開一個 **Bash** console，依序執行：

```bash
git clone https://github.com/11446006-Asher-Yu/timetable.git
cd timetable
mkvirtualenv --python=python3.12 timetable-venv   # 版本號換成你在 0. 確認的版本
pip install -r requirements.txt
```

`mkvirtualenv` 完成後，提示字元前面會出現 `(timetable-venv)`。之後重開 console 要先執行 `workon timetable-venv`。

## 2. 建立 .env（機密設定，不會上傳 GitHub）

先產生一組新的金鑰，**不要沿用本機的那組**：

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

再用編輯器建立 `.env`：

```bash
nano .env
```

內容如下，`<帳號>` 和金鑰換成實際值：

```
DJANGO_SECRET_KEY=剛才產生的那串金鑰
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=<帳號>.pythonanywhere.com

# 要測試忘記密碼寄信時才填，留白則信件不會寄出
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

存檔：`Ctrl+O` → `Enter` → `Ctrl+X`。

## 3. 建立資料庫、匯入節次、整理靜態檔

```bash
python manage.py migrate
python manage.py loaddata periods
python manage.py collectstatic --noinput
python manage.py createsuperuser   # 建立後台管理員，密碼自己設定
```

## 4. 設定網站（Web 頁面）

1. 到 **Web** 頁面，按 **Add a new web app**。
2. 網域選預設的 `<帳號>.pythonanywhere.com`。
3. 框架選 **Manual configuration**（不要選「Django」，那個選項會另外建一個新專案）。
4. Python 版本選和第 1 步 `mkvirtualenv` 相同的版本。
5. 建立完成後，在 Web 頁面設定以下項目：

| 區塊 | 欄位 | 填入 |
|---|---|---|
| Code | Source code | `/home/<帳號>/timetable` |
| Code | Working directory | `/home/<帳號>/timetable` |
| Virtualenv | 路徑 | `/home/<帳號>/.virtualenvs/timetable-venv` |
| Static files | URL：`/static/` | Directory：`/home/<帳號>/timetable/staticfiles` |
| Security | Force HTTPS（待確認：有這個選項就開啟） | Enabled |

6. 點 **Code** 區塊裡的 **WSGI configuration file** 連結（檔名類似 `/var/www/<帳號>_pythonanywhere_com_wsgi.py`），**把內容全部刪掉**，換成：

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
- [ ] 開啟分享，用無痕視窗開分享連結；**分享網址開頭要是 `https://`**
- [ ] 忘記密碼（有填 Gmail 時）：確認信件能寄到。待確認：免費方案能否連到 Gmail 寄信
- [ ] `https://<帳號>.pythonanywhere.com/admin/` 能用管理員帳號登入

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

- 免費網站有使用期限，Web 頁面會顯示到期日，要定期回來按延長的按鈕，否則網站會停用。**繳交後、老師評分前記得確認還沒到期。**
- 免費方案對外連線有限制，寄信（Gmail）是否可用要實測。
