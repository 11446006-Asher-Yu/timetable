// 課表頁：課程詳細資料視窗、標出今天與上課中的課、手機版星期分頁、列印與匯出圖片
(function () {
  const details = JSON.parse(document.getElementById('course-details').textContent);
  const dialog = document.getElementById('course-dialog');

  // ===== 詳細資料視窗 =====
  function setText(id, value) {
    document.getElementById(id).textContent = value || '—';
  }

  function openDialog(courseId) {
    const course = details[courseId];
    if (!course) return;
    setText('dialog-title', course.name);
    const tag = document.getElementById('dialog-category');
    tag.textContent = course.category;
    tag.style.background = course.color;
    document.getElementById('dialog-header').style.setProperty('--course-color', course.color);
    setText('dialog-teacher', course.teacher);
    setText('dialog-classroom', course.classroom);
    setText('dialog-credits', `${course.credits} 學分`);
    setText('dialog-times', course.times.join('、'));
    setText('dialog-note', course.note);

    // 分享頁（唯讀）沒有修改、刪除網址，整列按鈕隱藏
    const actions = document.getElementById('dialog-actions');
    actions.hidden = !course.edit_url;
    if (course.edit_url) {
      document.getElementById('dialog-edit').href = course.edit_url;
      document.getElementById('dialog-delete').href = course.delete_url;
    }
    dialog.showModal();
  }

  // 電腦版方塊與手機版卡片都帶有 data-course-id
  document.querySelectorAll('.tt-course, .m-course').forEach(function (block) {
    block.addEventListener('click', function (event) {
      event.preventDefault();
      openDialog(block.dataset.courseId);
    });
  });

  dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());
  // 點視窗外的灰色背景也能關閉
  dialog.addEventListener('click', function (event) {
    if (event.target === dialog) dialog.close();
  });

  // ===== 標出今天與上課中 =====
  // 一律以台灣時間判斷，即使使用者的裝置設在其他時區
  function taipeiNow(date) {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Taipei',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date);
    const get = (type) => parts.find((p) => p.type === type).value;
    const weekdays = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 };
    return { weekday: weekdays[get('weekday')], time: `${get('hour')}:${get('minute')}` };
  }

  function currentPeriod(time) {
    // "HH:MM" 字串可以直接比大小
    const row = [...document.querySelectorAll('.tt-period')].find(
      (p) => p.dataset.start <= time && time < p.dataset.end
    );
    return row ? Number(row.dataset.number) : null;
  }

  function highlight(date) {
    const now = taipeiNow(date || new Date());
    const period = currentPeriod(now.time);

    document.querySelectorAll('.tt-day, .tt-cell').forEach(function (el) {
      el.classList.toggle('is-today', Number(el.dataset.weekday) === now.weekday);
    });
    document.querySelectorAll('.tt-period').forEach(function (el) {
      el.classList.toggle('is-now', Number(el.dataset.number) === period);
    });
    document.querySelectorAll('.tt-course, .m-course').forEach(function (el) {
      const isCurrent = period !== null
        && Number(el.dataset.weekday) === now.weekday
        && Number(el.dataset.start) <= period
        && period <= Number(el.dataset.end);
      el.classList.toggle('is-current', isCurrent);
    });
  }

  highlight();
  setInterval(() => highlight(), 60 * 1000);
  // 方便在瀏覽器主控台測試，例如 timetableHighlight(new Date('2026-10-28T10:30:00+08:00'))
  window.timetableHighlight = highlight;

  // ===== 手機版星期分頁 =====
  // 沒有 JavaScript 時各天依序全部列出；有 JavaScript 才切換成分頁
  const tabs = [...document.querySelectorAll('.day-tab')];
  const panels = [...document.querySelectorAll('.day-panel')];

  function selectDay(weekday) {
    tabs.forEach(function (tab) {
      const selected = tab.dataset.weekday === String(weekday);
      tab.classList.toggle('is-selected', selected);
      tab.setAttribute('aria-selected', selected);
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.dataset.weekday !== String(weekday);
    });
  }

  if (tabs.length) {
    document.querySelector('.mobile-days').classList.add('is-tabbed');
    tabs.forEach((tab) => tab.addEventListener('click', () => selectDay(tab.dataset.weekday)));
    // 預設停在今天；今天不在分頁中（例如沒課的週日）就停在第一天
    const today = taipeiNow(new Date()).weekday;
    selectDay(tabs.some((tab) => tab.dataset.weekday === String(today)) ? today : tabs[0].dataset.weekday);
  }

  // ===== 列印 =====
  document.getElementById('print-button').addEventListener('click', () => window.print());

  // ===== 匯出圖片 =====
  const exportButton = document.getElementById('export-button');
  exportButton.addEventListener('click', async function () {
    if (typeof html2canvas !== 'function') {
      alert('匯出元件載入失敗，請確認網路連線後重新整理頁面。');
      return;
    }
    exportButton.disabled = true;
    exportButton.textContent = '匯出中…';
    try {
      const canvas = await html2canvas(document.getElementById('export-area'), {
        backgroundColor: '#FFFFFF',
        scale: 2, // 2 倍解析度，圖片在手機上看比較清楚
        // 在複製出來的頁面上切換成匯出模式：強制顯示完整格子、拿掉今天與上課中標示
        onclone: (doc) => doc.documentElement.classList.add('is-exporting'),
      });
      const link = document.createElement('a');
      link.download = '我的課表.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (error) {
      console.error(error);
      alert('匯出圖片失敗，請稍後再試。');
    } finally {
      exportButton.disabled = false;
      exportButton.textContent = '匯出圖片';
    }
  });
})();
