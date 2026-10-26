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

## 語言（英文為主，可切換繁體中文）

- 介面預設英文，頁首的「中文／EN」按鈕可切換，選擇記在瀏覽器 Cookie。
- 程式碼與模板裡寫英文，中文翻譯在 `locale/zh_Hant/LC_MESSAGES/django.po`。
- 新增或修改介面文字後：

```bash
pip install -r requirements-dev.txt
python scripts/i18n_tools.py extract   # 列出缺少翻譯的字串（標 ✗）
python scripts/i18n_tools.py compile   # 編譯成 django.mo
```

`django.mo` 要一起 commit，伺服器不需要安裝 Babel。

## 部署

部署到 PythonAnywhere 的步驟見 [DEPLOY.md](DEPLOY.md)。
