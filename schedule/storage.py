from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class LenientManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """找不到雜湊對照表時退回原檔名，而不是報錯。

    執行測試時沒有跑 collectstatic，用預設的嚴格模式會讓所有用到 {% static %} 的頁面出錯。
    """

    manifest_strict = False
