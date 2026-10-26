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
    button.textContent = '已複製！';
    setTimeout(() => { button.textContent = '複製連結'; }, 2000);
  });
})();
