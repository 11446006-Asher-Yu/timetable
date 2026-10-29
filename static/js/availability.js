// 可授課時段：把每格的下拉選單換成「點一下切換」的按鈕（可以 → 盡量避免 → 不行）
(function () {
  const form = document.getElementById('availability-form');
  if (!form || !form.classList.contains('is-editable')) return;
  const marks = { available: '✓', avoid: '~', unavailable: '✗' };
  const order = ['available', 'avoid', 'unavailable'];
  const selects = [...form.querySelectorAll('.avail-select')];

  function paint(button, select) {
    const value = select.value;
    button.className = `avail-toggle avail-${value}`;
    button.textContent = marks[value];
    button.setAttribute('aria-label', `${select.getAttribute('aria-label')}: ${select.selectedOptions[0].text}`);
  }

  selects.forEach(function (select) {
    const button = document.createElement('button');
    button.type = 'button';
    paint(button, select);
    button.addEventListener('click', function () {
      select.value = order[(order.indexOf(select.value) + 1) % order.length];
      paint(button, select);
    });
    select.hidden = true;
    select.insertAdjacentElement('afterend', button);
    select.button = button;
  });

  document.getElementById('all-available').addEventListener('click', function () {
    selects.forEach(function (select) {
      select.value = 'available';
      paint(select.button, select);
    });
  });
})();
