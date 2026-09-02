// 전체 문서를 담은 자체완결 단일 HTML 파일 생성기
// - CSS / JS / 아이콘 전부 인라인, 외부 요청 0건 → file:// 로 열어도 그대로 동작
// - 페이지 전환은 해시 라우팅(#/python), 인쇄하면 전체 문서가 한 번에 나옴
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { site, tree, flatten } from './nav.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const CONTENT = path.join(ROOT, 'content');
const PUBLIC = path.join(ROOT, 'public');
const DIST = path.join(ROOT, 'dist');
const OUT = path.join(DIST, 'mail-guide.html');

const pages = flatten();

/* ---------- helpers ---------- */

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const toText = (s) =>
  s
    .replace(/<[^>]+>/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();

// 모든 페이지가 한 문서 안에 들어가므로 heading id 앞에 페이지 키를 붙여 충돌을 막는다
const keyOf = (slug) => (slug === '' ? 'home' : slug.replace(/\//g, '-'));

function slugifyHeading(text) {
  return (
    text
      .replace(/<[^>]+>/g, '')
      .trim()
      .toLowerCase()
      .replace(/[^\p{Letter}\p{Number}\s-]/gu, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '') || 'section'
  );
}

function processHeadings(html, pageKey) {
  const toc = [];
  const used = new Map();
  const out = html.replace(/<(h2|h3|h4)([^>]*)>([\s\S]*?)<\/\1>/g, (m, tag, attrs, inner) => {
    const explicit = attrs.match(/\bid="([^"]+)"/);
    let id;
    if (explicit) {
      id = explicit[1];
      attrs = attrs.replace(/\bid="[^"]+"/, '');
    } else {
      id = slugifyHeading(inner);
      const n = (used.get(id) || 0) + 1;
      used.set(id, n);
      if (n > 1) id = `${id}-${n}`;
    }
    const full = `${pageKey}--${id}`;
    // h4 는 앵커만 부여하고 우측 목차에는 넣지 않는다
    if (tag !== 'h4') toc.push({ id: full, tag, text: toText(inner) });
    return `<${tag} id="${full}"${attrs}><a class="anchor" href="#${full}" aria-label="이 항목 링크">#</a>${inner}</${tag}>`;
  });
  return { html: out, toc };
}

// 사이트용 경로 링크를 단일 파일용 해시 링크로 변환
function rewriteLinks(html, pageKey) {
  return html
    .replace(/href="#([^"]+)"/g, (m, a) => `href="#${pageKey}--${a}"`)
    .replace(/href="\/([^"#]*)#([^"]+)"/g, (m, p, a) => `href="#${keyOf(p)}--${a}"`)
    .replace(/href="\/([^"]*)"/g, (m, p) => `href="#/${p}"`);
}

/* ---------- 사이드바 ---------- */

function renderNav(nodes, depth = 0) {
  let out = `<ul class="nav-list depth-${depth}">`;
  for (const n of nodes) {
    out += `<li class="nav-item${n.children ? ' has-children' : ''}">`;
    out += `<a class="nav-link" data-slug="${esc(n.slug)}" href="#/${n.slug}">`;
    out += n.children ? `<span class="nav-caret" aria-hidden="true"></span>` : `<span class="nav-dot" aria-hidden="true"></span>`;
    out += `<span class="nav-text">${esc(n.short || n.title)}</span></a>`;
    if (n.children) out += renderNav(n.children, depth + 1);
    out += `</li>`;
  }
  return out + `</ul>`;
}

function crumbsFor(slug) {
  const parts = [];
  const walk = (nodes, trail) => {
    for (const n of nodes) {
      const next = [...trail, n];
      if (n.slug === slug) { parts.push(...next); return true; }
      if (n.children && walk(n.children, next)) return true;
    }
    return false;
  };
  walk(tree, []);
  return parts;
}

/* ---------- 단일 파일 전용 스타일 ---------- */

const extraCss = `
/* ===== 단일 HTML 전용 ===== */
.main { display: block; }
.doc-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--toc-w);
  gap: 40px;
  align-items: start;
}
.doc-page[hidden] { display: none; }
.page-sep { display: none; }

.download-note {
  display: flex; gap: 11px; align-items: flex-start;
  margin: 0 0 26px; padding: 12px 15px;
  border: 1px dashed var(--border-strong); border-radius: 8px;
  background: var(--bg-subtle); color: var(--text-muted);
  font-size: 13.3px; line-height: 1.65;
}

@media (max-width: 1180px) {
  .doc-page { grid-template-columns: minmax(0, 1fr); }
}

/* ===== 인쇄 / PDF 저장: 전체 문서를 한 번에 ===== */
@media print {
  :root { --topbar-h: 0px; }
  .topbar, .sidebar, .sidebar-scrim, .toc, .pager, .footer,
  .anchor, .copy-btn, .download-note, .skip { display: none !important; }
  .layout { display: block; max-width: none; }
  .main { padding: 0; }
  .doc-page { display: block !important; page-break-after: always; }
  .doc-page:last-child { page-break-after: auto; }
  .doc { max-width: none; }
  .page-sep { display: block; }
  body { font-size: 11pt; background: #fff; color: #000; }
  .doc pre { background: #f4f5f7; color: #1b2130; border: 1px solid #ddd; white-space: pre-wrap; word-break: break-all; }
  .doc h1 { font-size: 20pt; }
  .doc h2 { font-size: 14pt; page-break-after: avoid; }
  .doc h3 { font-size: 12pt; page-break-after: avoid; }
  .table-wrap { overflow: visible; }
  a { color: inherit; text-decoration: none; }
}
`;

/* ---------- 인라인 스크립트 ---------- */

const inlineJs = `
(function () {
  'use strict';
  var root = document.documentElement;

  /* 테마 */
  var themeBtn = document.getElementById('themeBtn');
  themeBtn.addEventListener('click', function () {
    var cur = root.dataset.theme ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var next = cur === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch (e) {}
  });

  /* 모바일 사이드바 */
  var sidebar = document.getElementById('sidebar');
  var menuBtn = document.getElementById('menuBtn');
  var scrim = document.getElementById('scrim');
  function setMenu(open) {
    sidebar.classList.toggle('open', open);
    scrim.hidden = !open;
    menuBtn.setAttribute('aria-expanded', String(open));
  }
  menuBtn.addEventListener('click', function () { setMenu(!sidebar.classList.contains('open')); });
  scrim.addEventListener('click', function () { setMenu(false); });

  /* 코드블록 복사 */
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
        navigator.clipboard.writeText(text).then(done, fallback);
      } else { fallback(); }
      function fallback() {
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

  /* 페이지 전환 (해시 라우팅) */
  var pagesEls = Array.prototype.slice.call(document.querySelectorAll('.doc-page'));
  var navLinks = Array.prototype.slice.call(document.querySelectorAll('.nav-link'));
  var bySlug = {};
  pagesEls.forEach(function (el) { bySlug[el.dataset.slug] = el; });

  function show(slug, scrollTo) {
    if (!(slug in bySlug)) slug = '';
    pagesEls.forEach(function (el) { el.hidden = el.dataset.slug !== slug; });
    navLinks.forEach(function (a) {
      var s = a.dataset.slug;
      var inPath = s !== '' && slug.indexOf(s + '/') === 0;
      a.classList.toggle('active', s === slug);
      a.classList.toggle('in-path', inPath);
    });
    document.title = bySlug[slug].dataset.title;
    if (scrollTo) {
      var el = document.getElementById(scrollTo);
      if (el) { el.scrollIntoView(); return; }
    }
    window.scrollTo(0, 0);
    syncToc();
  }

  function route() {
    var h = decodeURIComponent(location.hash || '');
    if (!h || h === '#') return show('');
    if (h.indexOf('#/') === 0) return show(h.slice(2));
    var id = h.slice(1);
    var target = document.getElementById(id);
    if (target) {
      var page = target.closest('.doc-page');
      return show(page ? page.dataset.slug : '', id);
    }
    show('');
  }

  window.addEventListener('hashchange', function () { route(); setMenu(false); });

  /* 페이지 내 목차 하이라이트 */
  var tocState = [];
  function syncToc() {
    var page = pagesEls.filter(function (el) { return !el.hidden; })[0];
    if (!page) { tocState = []; return; }
    var links = Array.prototype.slice.call(page.querySelectorAll('.toc a'));
    tocState = links.map(function (a) {
      return { a: a, el: document.getElementById(decodeURIComponent(a.hash.slice(1))) };
    }).filter(function (x) { return x.el; });
    onScroll();
  }
  function onScroll() {
    if (!tocState.length) return;
    var y = window.scrollY + 110;
    var cur = tocState[0];
    tocState.forEach(function (x) { if (x.el.offsetTop <= y) cur = x; });
    tocState.forEach(function (x) { x.a.classList.toggle('active', x === cur); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });

  /* 문서 필터 (오프라인이므로 인덱스도 문서 안에 있음) */
  var input = document.getElementById('search');
  var results = document.getElementById('searchResults');
  var sel = -1;

  function escapeHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function highlight(text, q) {
    var i = text.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, i)) + '<mark>' + escapeHtml(text.slice(i, i + q.length)) +
           '</mark>' + escapeHtml(text.slice(i + q.length));
  }
  function snippet(body, q) {
    var i = body.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return '';
    var start = Math.max(0, i - 40);
    return (start > 0 ? '…' : '') + highlight(body.slice(start, i + q.length + 70).trim(), q) + '…';
  }
  function search(q) {
    var ql = q.toLowerCase().trim();
    if (!ql) return [];
    return SEARCH_INDEX.map(function (p) {
      var score = 0, where = '', hh = null;
      if (p.t.toLowerCase().indexOf(ql) >= 0) { score += 100; where = 'title'; }
      if (p.d.toLowerCase().indexOf(ql) >= 0) { score += 40; where = where || 'desc'; }
      for (var i = 0; i < p.h.length; i++) {
        if (p.h[i].text.toLowerCase().indexOf(ql) >= 0) { hh = p.h[i]; score += 25; where = where || 'heading'; break; }
      }
      if (p.b.toLowerCase().indexOf(ql) >= 0) { score += 8; where = where || 'body'; }
      return { p: p, score: score, where: where, heading: hh };
    }).filter(function (r) { return r.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, 8);
  }
  function render(list, q) {
    if (!list.length) {
      results.innerHTML = '<div class="sr-empty">검색 결과가 없습니다</div>';
    } else {
      results.innerHTML = list.map(function (r, i) {
        var href = r.where === 'heading' && r.heading ? '#' + r.heading.id : '#/' + r.p.u;
        var sub = r.where === 'heading' && r.heading ? highlight(r.heading.text, q)
                : (r.where === 'body' ? snippet(r.p.b, q) : escapeHtml(r.p.d));
        return '<a class="sr-item' + (i === sel ? ' sel' : '') + '" href="' + href + '">' +
          '<div class="sr-title">' + highlight(r.p.t, q) + '</div>' +
          (sub ? '<div class="sr-desc">' + sub + '</div>' : '') + '</a>';
      }).join('');
    }
    results.hidden = false;
  }
  input.addEventListener('input', function () {
    var q = input.value;
    if (!q.trim()) { results.hidden = true; return; }
    sel = -1;
    render(search(q), q);
  });
  input.addEventListener('keydown', function (e) {
    var items = results.querySelectorAll('.sr-item');
    if (e.key === 'Escape') { results.hidden = true; input.blur(); return; }
    if (!items.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sel = e.key === 'ArrowDown' ? Math.min(sel + 1, items.length - 1) : Math.max(sel - 1, 0);
      items.forEach(function (el, i) { el.classList.toggle('sel', i === sel); });
      items[sel].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter' && sel >= 0) {
      e.preventDefault();
      items[sel].click();
      results.hidden = true;
    }
  });
  results.addEventListener('click', function () { results.hidden = true; });
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

  route();
})();
`;

/* ---------- 실행 ---------- */

async function main() {
  const css = await readFile(path.join(PUBLIC, 'styles.css'), 'utf8');
  const index = [];
  let sections = '';

  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    const key = keyOf(page.slug);
    const raw = await readFile(path.join(CONTENT, page.file), 'utf8');
    // 링크를 먼저 해시 형태로 바꾼 뒤 heading id 를 부여한다
    // (순서가 바뀌면 processHeadings 가 만든 앵커 링크에 접두어가 두 번 붙는다)
    const { html: body, toc } = processHeadings(rewriteLinks(raw, key), key);

    const crumbs = crumbsFor(page.slug);
    const crumbHtml = crumbs
      .map((c, n) =>
        n === crumbs.length - 1
          ? `<span aria-current="page">${esc(c.short || c.title)}</span>`
          : `<a href="#/${c.slug}">${esc(c.short || c.title)}</a><span class="sep">/</span>`
      )
      .join('');

    const tocHtml = toc.length
      ? `<nav class="toc" aria-label="이 페이지 목차">
          <div class="toc-title">이 페이지 목차</div>
          <ul>${toc.map((t) => `<li class="toc-${t.tag}"><a href="#${t.id}">${esc(t.text)}</a></li>`).join('')}</ul>
        </nav>`
      : '';

    const prev = pages[i - 1];
    const next = pages[i + 1];
    const pagerHtml = `<nav class="pager" aria-label="이전/다음 문서">
        ${prev ? `<a class="pager-link prev" href="#/${prev.slug}"><span class="pager-dir">← 이전</span><span class="pager-title">${esc(prev.title)}</span></a>` : '<span></span>'}
        ${next ? `<a class="pager-link next" href="#/${next.slug}"><span class="pager-dir">다음 →</span><span class="pager-title">${esc(next.title)}</span></a>` : '<span></span>'}
      </nav>`;

    const note =
      page.slug === ''
        ? `<div class="download-note">
             <span aria-hidden="true">💾</span>
             <div>이 파일 하나에 전체 문서가 들어 있습니다. 인터넷 연결 없이 열람할 수 있고,
             브라우저에서 <strong>인쇄(⌘P / Ctrl+P)</strong> 하면 모든 문서가 이어진 한 권으로 출력·PDF 저장됩니다.</div>
           </div>`
        : '';

    sections += `
    <section class="doc-page" data-slug="${esc(page.slug)}" data-title="${esc(page.slug === '' ? site.title : page.title + ' · ' + site.title)}" hidden>
      <article class="doc">
        <nav class="crumbs" aria-label="현재 위치">${crumbHtml}</nav>
        ${note}
        ${body}
        ${pagerHtml}
      </article>
      ${tocHtml}
    </section>`;

    index.push({
      t: page.title,
      u: page.slug,
      d: page.desc || '',
      h: toc.map((t) => ({ id: t.id, text: t.text })),
      b: toText(body).slice(0, 4000),
    });
  }

  const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(site.title)}</title>
<meta name="description" content="${esc(site.description)}">
<link rel="icon" href="data:image/svg+xml,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#2f5bd7"/><g fill="none" stroke="#fff" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><rect x="6.5" y="9.5" width="19" height="13" rx="2"/><path d="m7.2 10.6 8.8 6.3 8.8-6.3"/></g></svg>'
  )}">
<style>
${css}
${extraCss}
</style>
<script>
  (function () {
    try {
      var t = localStorage.getItem('theme');
      if (t) document.documentElement.dataset.theme = t;
    } catch (e) {}
  })();
</script>
</head>
<body>
<a class="skip" href="#/">본문으로 건너뛰기</a>

<header class="topbar">
  <button class="icon-btn menu-btn" id="menuBtn" aria-label="문서 목록 열기" aria-expanded="false">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
  </button>
  <a class="brand" href="#/">
    <span class="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h15A1.5 1.5 0 0 1 21 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/><path d="m3.6 6.9 8.4 6 8.4-6"/></svg>
    </span>
    <span class="brand-text">메일발송서버 <b>이용가이드</b></span>
  </a>
  <div class="topbar-spacer"></div>
  <div class="search-wrap">
    <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input id="search" type="search" placeholder="문서 검색  (/)" aria-label="문서 검색" autocomplete="off">
    <div class="search-results" id="searchResults" role="listbox" hidden></div>
  </div>
  <button class="icon-btn theme-btn" id="themeBtn" aria-label="테마 전환">
    <svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M19.1 4.9l-1.7 1.7M6.6 17.4l-1.7 1.7"/></svg>
    <svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2z"/></svg>
  </button>
</header>

<div class="layout">
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-inner">
      <div class="sidebar-title">문서</div>
      ${renderNav(tree)}
    </div>
  </aside>
  <div class="sidebar-scrim" id="scrim" hidden></div>

  <main class="main" id="main">${sections}
  </main>
</div>

<footer class="footer">
  <span>메일파트 공용 메일 발송 서버(KMH) 문서 · 사내 참고용 · 단일 HTML 배포판</span>
</footer>

<script>
var SEARCH_INDEX = ${JSON.stringify(index)};
${inlineJs}
</script>
</body>
</html>`;

  await mkdir(DIST, { recursive: true });
  await writeFile(OUT, html);

  const kb = (Buffer.byteLength(html) / 1024).toFixed(0);
  console.log(`  ✓ ${path.relative(ROOT, OUT)}  (${pages.length}개 문서, ${kb} KB, 외부 요청 0건)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
