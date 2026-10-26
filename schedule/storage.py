from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class LenientManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """找不到雜湊檔名時退回原檔名，而不是報錯。

    執行測試、或新增檔案後還沒重跑 collectstatic 時，預設的嚴格模式會讓所有用到
    {% static %} 的頁面出錯（500）。退回原檔名頂多少了快取效果，網站仍能正常顯示。
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            return name
