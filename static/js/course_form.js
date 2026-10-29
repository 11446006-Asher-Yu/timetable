// 課程表單：新增上課時段、隱藏已勾選刪除的時段、顏色選擇器
(function () {
  const rows = document.getElementById('time-rows');
  const template = document.getElementById('time-row-template');
  const addButton = document.getElementById('add-time');
  const totalForms = document.querySelector('input[name$="-TOTAL_FORMS"]');

  // 勾選「刪除」的時段整列隱藏，取消勾選再顯示
  function bindDelete(row) {
    const checkbox = row.querySelector('input[name$="-DELETE"]');
    if (!checkbox) return;
    const update = () => row.classList.toggle('is-deleted', checkbox.checked);
    checkbox.addEventListener('change', update);
    update();
  }

  // 正式課程的修改頁沒有時段欄位，跳過這段
  if (rows) {
    rows.querySelectorAll('.time-row').forEach(bindDelete);

    // Django formset 的空白表單以 __prefix__ 標記索引，複製時換成下一個編號
    addButton.addEventListener('click', function () {
      const index = Number(totalForms.value);
      const html = template.innerHTML.replace(/__prefix__/g, index);
      rows.insertAdjacentHTML('beforeend', html);
      totalForms.value = index + 1;
      bindDelete(rows.lastElementChild);
    });
  }

  // 色碼文字欄旁加上原生顏色選擇器，兩邊同步；文字欄留白代表使用類別預設色
  const colorInput = document.querySelector('input[name="color"]');
  if (colorInput) {
    const picker = document.createElement('input');
    picker.type = 'color';
    picker.className = 'color-picker';
    picker.value = /^#[0-9a-f]{6}$/i.test(colorInput.value) ? colorInput.value : '#4f86c6';
    picker.addEventListener('input', () => { colorInput.value = picker.value.toUpperCase(); });
    colorInput.addEventListener('input', () => {
      if (/^#[0-9a-f]{6}$/i.test(colorInput.value)) picker.value = colorInput.value;
    });
    colorInput.insertAdjacentElement('afterend', picker);
    colorInput.parentElement.classList.add('has-color-picker');
  }
})();
