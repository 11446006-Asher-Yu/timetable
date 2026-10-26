# 線上個人課表系統

網頁程式設計課程期末作業，使用 Django 開發。規劃書見上一層的 `線上個人課表系統_規劃書.md`。

## 本機執行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # 再把 DJANGO_SECRET_KEY 改成隨機字串
python manage.py migrate
python manage.py loaddata periods   # 匯入節次資料
python manage.py runserver
```

開啟 http://127.0.0.1:8000/

## 部署

部署到 PythonAnywhere 的步驟見 [DEPLOY.md](DEPLOY.md)。
