// 課表頁：課程詳細資料視窗、標出今天與上課中的課
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

  document.querySelectorAll('.tt-course').forEach(function (block) {
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
    document.querySelectorAll('.tt-course').forEach(function (el) {
      const isCurrent = period !== null
        && Number(el.dataset.weekday) === now.weekday
        && Number(el.dataset.start) <= period
        && period <= Number(el.dataset.end);
      el.classList.toggle('is-current', isCurrent);
    });
  }

  highlight();
  setInterval(highlight, 60 * 1000);
  // 方便在瀏覽器主控台測試，例如 timetableHighlight(new Date('2026-10-28T10:30:00+08:00'))
  window.timetableHighlight = highlight;
})();
