"""翻譯檔小工具（電腦上沒有 GNU gettext 時用來代替 makemessages／compilemessages）。

    python scripts/i18n_tools.py extract   列出程式碼與模板中所有要翻譯的字串，並標出翻譯檔缺少的
    python scripts/i18n_tools.py compile   把 django.po 編譯成 django.mo（需要先 pip install -r requirements-dev.txt）

編譯好的 django.mo 會一起 commit，伺服器上不需要安裝 Babel。
"""

import ast
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PO_FILE = BASE_DIR / 'locale' / 'zh_Hant' / 'LC_MESSAGES' / 'django.po'
MO_FILE = PO_FILE.with_suffix('.mo')

PY_FUNCS = {'_', 'gettext', 'gettext_lazy', 'pgettext', 'pgettext_lazy', 'ngettext', 'ngettext_lazy'}

TRANSLATE_TAG = re.compile(
    r"""{%\s*translate\s+(?P<q>["'])(?P<msg>.*?)(?P=q)(?:\s+context\s+(?P<cq>["'])(?P<ctx>.*?)(?P=cq))?\s*%}"""
)
BLOCK_TAG = re.compile(
    r'{%\s*blocktranslate(?P<args>[^%]*)%}(?P<body>.*?){%\s*endblocktranslate\s*%}', re.S
)
VAR = re.compile(r'{{\s*(\w+)\s*}}')


def _block_msg(text):
    # 和 Django 相同：{{ name }} 換成 %(name)s，字面上的 % 變成 %%
    return VAR.sub(r'%(\1)s', text.replace('%', '%%'))


def extract():
    """回傳 {(context, msgid, plural): 出處}。"""
    found = {}

    py_files = [p for app in ('schedule', 'scheduling') for p in (BASE_DIR / app).rglob('*.py')]
    for path in sorted(py_files):
        if 'migrations' in path.parts or path.name == 'tests.py':
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in PY_FUNCS):
                continue
            args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if node.func.id.startswith('pgettext') and len(args) == 2:
                found[(args[0], args[1], None)] = path.name
            elif node.func.id.startswith('ngettext') and len(args) >= 2:
                found[(None, args[0], args[1])] = path.name
            elif args:
                found[(None, args[0], None)] = path.name

    for path in sorted((BASE_DIR / 'templates').rglob('*')):
        if path.suffix not in ('.html', '.txt'):
            continue
        source = path.read_text(encoding='utf-8')
        for match in TRANSLATE_TAG.finditer(source):
            # Django 的 translate 標籤查翻譯前會把 % 變成 %%，這裡照做，翻譯檔才對得上
            found[(match['ctx'], match['msg'].replace('%', '%%'), None)] = path.name
        for match in BLOCK_TAG.finditer(source):
            body = match['body']
            if '{% plural %}' in body:
                singular, plural = body.split('{% plural %}')
                found[(None, _block_msg(singular), _block_msg(plural))] = path.name
            else:
                found[(None, _block_msg(body), None)] = path.name
    return found


def read_po():
    """簡易讀取 .po：回傳 {(context, msgid): 是否已翻譯}。"""
    entries, current = {}, {}

    def flush():
        if 'msgid' in current and current['msgid']:
            translated = any(v for k, v in current.items() if k.startswith('msgstr'))
            entries[(current.get('msgctxt'), current['msgid'])] = translated
        current.clear()

    key = None
    for line in PO_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            flush()
            key = None
            continue
        if line.startswith('#'):
            continue
        match = re.match(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d\])?)\s+"(.*)"$', line)
        if match:
            key = match[1]
            if key == 'msgid' and 'msgid' in current:
                flush()
            current[key] = ast.literal_eval(f'"{match[2]}"')
        elif line.startswith('"') and key:
            current[key] += ast.literal_eval(line)
    flush()
    return entries


def main(command):
    if command == 'extract':
        po = read_po() if PO_FILE.exists() else {}
        missing = 0
        for (ctx, msg, plural), where in sorted(extract().items(), key=lambda i: i[1]):
            ok = po.get((ctx, msg), False)
            missing += not ok
            mark = '  ' if ok else '✗ '
            print(f'{mark}[{where}] {f"({ctx}) " if ctx else ""}{msg!r}{f" / {plural!r}" if plural else ""}')
        print(f'\n缺少翻譯：{missing} 筆')
        return 1 if missing else 0
    if command == 'compile':
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po as babel_read_po

        with PO_FILE.open('rb') as f:
            catalog = babel_read_po(f, locale='zh_Hant')
        with MO_FILE.open('wb') as f:
            write_mo(f, catalog)
        print(f'已編譯 {MO_FILE.relative_to(BASE_DIR)}（{len(catalog)} 筆）')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
