// 排課看板：勾選時段或換教室時，即時向伺服器檢查衝堂並更新教室選單
// 沒有 JavaScript 時，勾選後按「Save draft」也會在頁面上顯示檢查結果
(function () {
  const form = document.getElementById('board-form');
  if (!form) return;
  const result = document.getElementById('check-result');
  const roomSelect = document.getElementById('classroom');
  const sendButton = document.getElementById('send-button');
  const text = JSON.parse(document.getElementById('board-text').textContent);
  let timer = null;
  let latest = 0;

  function line(className, mark, message) {
    const p = document.createElement('p');
    p.className = `check ${className}`;
    p.textContent = `${mark} ${message}`;
    return p;
  }

  function render(data) {
    result.replaceChildren(
      ...data.errors.map((m) => line('check-error', '✗', m)),
      ...data.warnings.map((m) => line('check-warning', '~', m)),
      ...(data.ok ? [line('check-ok', '✓', text.ok)] : [])
    );
    // 教室選單換成目前時段可用的教室，保留原本的選擇
    const current = roomSelect.value;
    const options = [new Option(text.select, '')].concat(
      data.rooms.map((room) => new Option(room.name, room.id, false, String(room.id) === current))
    );
    roomSelect.replaceChildren(...options);
    sendButton.classList.toggle('is-blocked', !data.ok);
  }

  async function check() {
    const request = ++latest;
    const body = new FormData(form);
    body.set('action', 'check');
    try {
      const response = await fetch(form.dataset.checkUrl, { method: 'POST', body });
      const data = await response.json();
      if (request === latest) render(data); // 只採用最後一次的結果
    } catch (error) {
      console.error(error);
    }
  }

  form.addEventListener('change', function () {
    clearTimeout(timer);
    timer = setTimeout(check, 150);
  });
})();
