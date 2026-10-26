from django.conf import settings
from django.utils import translation


class CookieLocaleMiddleware:
    """只依使用者在頁首選的語言（Cookie）決定介面語言，沒選過就用英文。

    Django 內建的 LocaleMiddleware 會參考瀏覽器語言，台灣使用者幾乎都會自動變成中文，
    不符合「英文為主」的需求，所以不用它。
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.supported = {code for code, _ in settings.LANGUAGES}

    def __call__(self, request):
        language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        if language not in self.supported:
            language = settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = language

        response = self.get_response(request)
        response.headers.setdefault('Content-Language', language)
        # 同一網址會因 Cookie 顯示不同語言，告訴快取不要混用
        response.headers['Vary'] = ', '.join(
            filter(None, [response.headers.get('Vary'), 'Cookie'])
        )
        translation.deactivate()
        return response
