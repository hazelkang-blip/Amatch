(function () {
  'use strict';

  /* ---------- 테마 ---------- */
  var root = document.documentElement;
  var themeBtn = document.getElementById('themeBtn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var current = root.dataset.theme;
      if (!current) {
        current = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      var next = current === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('theme', next); } catch (e) {}
    });
  }

  /* ---------- 모바일 사이드바 ---------- */
  var sidebar = document.getElementById('sidebar');
  var menuBtn = document.getElementById('menuBtn');
  var scrim = document.getElementById('scrim');
  function setMenu(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('open', open);
    if (scrim) scrim.hidden = !open;
    if (menuBtn) menuBtn.setAttribute('aria-expanded', String(open));
  }
  if (menuBtn) menuBtn.addEventListener('click', function () { setMenu(!sidebar.classList.contains('open')); });
  if (scrim) scrim.addEventListener('click', function () { setMenu(false); });
  setMenu(false);

  /* ---------- 활성 사이드바 항목 스크롤 ---------- */
  var active = document.querySelector('.nav-link.active');
  if (active && sidebar && sidebar.scrollHeight > sidebar.clientHeight) {
    var top = active.offsetTop - sidebar.clientHeight / 2;
    if (top > 0) sidebar.scrollTop = top;
  }

  /* ---------- 코드블록 복사 버튼 ---------- */
  document.querySelectorAll('.codeblock').forEach(function (block) {
    var pre = block.querySelector('pre');
    if (!pre) return;
    var head = block.querySelector('.codeblock-head');
    if (!head) {
      head = document.createElement('div');
      head.className = 'codeblock-head';
      head.innerHTML = '<span class="codeblock-lang"></span>';
      block.insertBefore(head, pre);
    }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = '복사';
    btn.addEventListener('click', function () {
      var text = pre.innerText;
      var done = function () {
        btn.textContent = '복사됨';
        btn.classList.add('done');
        setTimeout(function () { btn.textContent = '복사'; btn.classList.remove('done'); }, 1500);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
    head.appendChild(btn);
  });

  /* ---------- 페이지 내 목차 하이라이트 ---------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc a'));
  if (tocLinks.length) {
    var targets = tocLinks
      .map(function (a) { return document.getElementById(decodeURIComponent(a.hash.slice(1))); })
      .filter(Boolean);
    var setActive = function (id) {
      tocLinks.forEach(function (a) {
        a.classList.toggle('active', decodeURIComponent(a.hash.slice(1)) === id);
      });
    };
    var onScroll = function () {
      var y = window.scrollY + 110;
      var cur = targets[0];
      for (var i = 0; i < targets.length; i++) {
        if (targets[i].offsetTop <= y) cur = targets[i];
      }
      if (cur) setActive(cur.id);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- 검색 ---------- */
  var input = document.getElementById('search');
  var results = document.getElementById('searchResults');
  var index = null;
  var sel = -1;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    return fetch('/search-index.json')
      .then(function (r) { return r.json(); })
      .then(function (d) { index = d; return d; })
      .catch(function () { index = []; return index; });
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function highlight(text, q) {
    var i = text.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, i)) + '<mark>' + escapeHtml(text.slice(i, i + q.length)) + '</mark>' + escapeHtml(text.slice(i + q.length));
  }

  function snippet(body, q) {
    var i = body.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return '';
    var start = Math.max(0, i - 40);
    var s = (start > 0 ? '…' : '') + body.slice(start, i + q.length + 70).trim() + '…';
    return highlight(s, q);
  }

  function search(q) {
    var ql = q.toLowerCase().trim();
    if (!ql) return [];
    return index
      .map(function (p) {
        var score = 0;
        var where = '';
        if (p.t.toLowerCase().indexOf(ql) >= 0) { score += 100; where = 'title'; }
        if (p.d.toLowerCase().indexOf(ql) >= 0) { score += 40; where = where || 'desc'; }
        var hh = p.h.find(function (h) { return h.toLowerCase().indexOf(ql) >= 0; });
        if (hh) { score += 25; where = where || 'heading'; }
        if (p.b.toLowerCase().indexOf(ql) >= 0) { score += 8; where = where || 'body'; }
        return { p: p, score: score, where: where, heading: hh };
      })
      .filter(function (r) { return r.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, 8);
  }

  function render(list, q) {
    if (!list.length) {
      results.innerHTML = '<div class="sr-empty">검색 결과가 없습니다</div>';
    } else {
      results.innerHTML = list
        .map(function (r, i) {
          var sub = r.where === 'heading' && r.heading
            ? highlight(r.heading, q)
            : (r.where === 'body' ? snippet(r.p.b, q) : escapeHtml(r.p.d));
          return '<a class="sr-item' + (i === sel ? ' sel' : '') + '" href="' + r.p.u + '">' +
            '<div class="sr-title">' + highlight(r.p.t, q) + '</div>' +
            (sub ? '<div class="sr-desc">' + sub + '</div>' : '') +
            '</a>';
        })
        .join('');
    }
    results.hidden = false;
  }

  if (input && results) {
    input.addEventListener('focus', loadIndex);
    input.addEventListener('input', function () {
      var q = input.value;
      if (!q.trim()) { results.hidden = true; return; }
      loadIndex().then(function () { sel = -1; render(search(q), q); });
    });
    input.addEventListener('keydown', function (e) {
      var items = results.querySelectorAll('.sr-item');
      if (e.key === 'Escape') { results.hidden = true; input.blur(); return; }
      if (!items.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        sel = e.key === 'ArrowDown'
          ? Math.min(sel + 1, items.length - 1)
          : Math.max(sel - 1, 0);
        items.forEach(function (el, i) { el.classList.toggle('sel', i === sel); });
        items[sel].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter' && sel >= 0) {
        e.preventDefault();
        window.location.href = items[sel].getAttribute('href');
      }
    });
    document.addEventListener('click', function (e) {
      if (!results.contains(e.target) && e.target !== input) results.hidden = true;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && document.activeElement !== input &&
          !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
        e.preventDefault();
        input.focus();
        input.select();
      }
    });
  }
})();
