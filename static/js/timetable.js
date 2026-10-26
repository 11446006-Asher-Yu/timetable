// 課表頁：課程詳細資料視窗、標出今天與上課中的課、手機版星期分頁、列印與匯出圖片
(function () {
  const details = JSON.parse(document.getElementById('course-details').textContent);
  const dialog = document.getElementById('course-dialog');
  // 系統設定「減少動態效果」時，JavaScript 動畫也一併略過
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ===== 詳細資料視窗 =====
  function setText(id, value) {
    document.getElementById(id).textContent = value || '—';
  }

  function openDialog(courseId, source) {
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

    // 從被點的方塊位置放大彈出：把縮放中心設在方塊中央
    if (reduceMotion.matches || !source) return;
    const from = source.getBoundingClientRect();
    const box = dialog.getBoundingClientRect();
    const originX = from.left + from.width / 2 - box.left;
    const originY = from.top + from.height / 2 - box.top;
    dialog.style.transformOrigin = `${originX}px ${originY}px`;
    dialog.animate(
      [{ transform: 'scale(0.4)', opacity: 0 }, { transform: 'scale(1)', opacity: 1 }],
      { duration: 380, easing: 'cubic-bezier(0.34, 1.3, 0.64, 1)' }
    );
  }

  let closing = false;
  function closeDialog() {
    if (!dialog.open || closing) return;
    if (reduceMotion.matches) {
      dialog.close();
      return;
    }
    closing = true;
    dialog.classList.add('is-closing');
    const animation = dialog.animate(
      [{ transform: 'scale(1)', opacity: 1 }, { transform: 'scale(0.9)', opacity: 0 }],
      { duration: 160, easing: 'cubic-bezier(0.4, 0, 1, 1)' }
    );
    animation.onfinish = function () {
      dialog.classList.remove('is-closing');
      dialog.close();
      closing = false;
    };
  }

  // 電腦版方塊與手機版卡片都帶有 data-course-id
  document.querySelectorAll('.tt-course, .m-course').forEach(function (block) {
    block.addEventListener('click', function (event) {
      event.preventDefault();
      openDialog(block.dataset.courseId, block);
    });
  });

  dialog.querySelector('[data-close]').addEventListener('click', closeDialog);
  // 點視窗外的灰色背景也能關閉
  dialog.addEventListener('click', function (event) {
    if (event.target === dialog) closeDialog();
  });
  // 按 Esc 時先播放關閉動畫，不讓瀏覽器直接關掉
  dialog.addEventListener('cancel', function (event) {
    event.preventDefault();
    closeDialog();
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
  const tabBar = document.querySelector('.day-tabs');
  let indicator = null;
  let selectedIndex = -1;

  // 選取底色像膠囊一樣滑到被選的星期
  function moveIndicator() {
    const tab = tabs[selectedIndex];
    if (!indicator || !tab || !tab.offsetWidth) return;
    indicator.style.width = `${tab.offsetWidth}px`;
    indicator.style.transform = `translateX(${tab.offsetLeft}px)`;
  }

  function selectDay(weekday) {
    const index = tabs.findIndex((tab) => tab.dataset.weekday === String(weekday));
    if (index === -1 || index === selectedIndex) return;
    const direction = selectedIndex === -1 ? 0 : Math.sign(index - selectedIndex);
    selectedIndex = index;

    tabs.forEach(function (tab, i) {
      tab.classList.toggle('is-selected', i === index);
      tab.setAttribute('aria-selected', i === index);
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.dataset.weekday !== String(weekday);
    });
    moveIndicator();

    // 往後一天從右邊滑入，往前一天從左邊滑入
    const panel = panels[index];
    if (direction && !reduceMotion.matches) {
      panel.animate(
        [{ opacity: 0, transform: `translateX(${direction * 32}px)` }, { opacity: 1, transform: 'none' }],
        { duration: 300, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' }
      );
    }
  }

  if (tabs.length) {
    document.querySelector('.mobile-days').classList.add('is-tabbed');
    indicator = document.createElement('span');
    indicator.className = 'day-tab-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    tabBar.prepend(indicator);
    tabBar.classList.add('has-indicator');

    tabs.forEach((tab) => tab.addEventListener('click', () => selectDay(tab.dataset.weekday)));
    // 預設停在今天；今天不在分頁中（例如沒課的週日）就停在第一天
    const today = taipeiNow(new Date()).weekday;
    selectDay(tabs.some((tab) => tab.dataset.weekday === String(today)) ? today : tabs[0].dataset.weekday);

    // 第一次定位不要有滑動動畫；之後切換才滑動
    requestAnimationFrame(() => indicator.classList.add('is-ready'));
    window.addEventListener('resize', moveIndicator);

    // 手指左右滑動切換星期（水平距離夠長、且比垂直距離明顯才算，避免干擾上下捲動）
    let touchStart = null;
    const swipeArea = document.querySelector('.mobile-days');
    swipeArea.addEventListener('touchstart', function (event) {
      const touch = event.touches[0];
      touchStart = { x: touch.clientX, y: touch.clientY };
    }, { passive: true });
    swipeArea.addEventListener('touchend', function (event) {
      if (!touchStart) return;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - touchStart.x;
      const dy = touch.clientY - touchStart.y;
      touchStart = null;
      if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
      const next = tabs[selectedIndex + (dx < 0 ? 1 : -1)];
      if (next) selectDay(next.dataset.weekday);
    });
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
