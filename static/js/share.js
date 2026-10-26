// 分享設定頁：複製分享連結
(function () {
  const button = document.getElementById('copy-button');
  if (!button) return;
  const input = document.getElementById('share-url');

  button.addEventListener('click', async function () {
    try {
      await navigator.clipboard.writeText(input.value);
    } catch (error) {
      // 不支援 Clipboard API（例如非 HTTPS）時，改用選取文字讓使用者自己複製
      input.select();
      document.execCommand('copy');
    }
    // 按鈕原本的文字與「已複製」都由頁面依目前語言提供
    const original = button.dataset.label || button.textContent;
    button.dataset.label = original;
    button.textContent = button.dataset.copied;
    setTimeout(() => { button.textContent = original; }, 2000);
  });
})();
