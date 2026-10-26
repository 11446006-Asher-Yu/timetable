// 全站共用：成功訊息顯示 4 秒後自動淡出
(function () {
  document.querySelectorAll('.message-success').forEach(function (message) {
    setTimeout(function () {
      message.classList.add('is-leaving');
      // 淡出完再移除；減少動態效果時 transitionend 仍會觸發，另設保險時間
      const remove = () => message.remove();
      message.addEventListener('transitionend', remove, { once: true });
      setTimeout(remove, 600);
    }, 4000);
  });
})();
