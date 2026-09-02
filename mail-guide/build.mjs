import { readFile, writeFile, mkdir, rm, readdir, copyFile, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { site, tree, flatten } from './nav.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const CONTENT = path.join(ROOT, 'content');
const PUBLIC = path.join(ROOT, 'public');
const DIST = path.join(ROOT, 'dist');

const pages = flatten();

/* ---------- helpers ---------- */

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// HTML 조각에서 순수 텍스트만 추출 (태그 제거 + 엔티티 복원)
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

// 한글/영문 제목을 앵커 id 로 변환
function slugifyHeading(text) {
  return text
    .replace(/<[^>]+>/g, '')
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'section';
}

// h2/h3 에 id 를 붙이고 페이지 내 목차를 추출
function processHeadings(html) {
  const toc = [];
  const used = new Map();
  const out = html.replace(/<(h2|h3)([^>]*)>([\s\S]*?)<\/\1>/g, (m, tag, attrs, inner) => {
    const explicit = attrs.match(/\bid="([^"]+)"/);
    if (explicit) {
      toc.push({ id: explicit[1], tag, text: toText(inner) });
      used.set(explicit[1], 1);
      return `<${tag}${attrs}><a class="anchor" href="#${explicit[1]}" aria-label="이 항목 링크">#</a>${inner}</${tag}>`;
    }
    let id = slugifyHeading(inner);
    const n = (used.get(id) || 0) + 1;
    used.set(id, n);
    if (n > 1) id = `${id}-${n}`;
    toc.push({ id, tag, text: toText(inner) });
    return `<${tag} id="${id}"${attrs}><a class="anchor" href="#${id}" aria-label="이 항목 링크">#</a>${inner}</${tag}>`;
  });
  return { html: out, toc };
}

function href(slug) {
  return '/' + slug;
}

/* ---------- 사이드바 ---------- */

function renderNav(nodes, current, depth = 0) {
  let out = `<ul class="nav-list depth-${depth}">`;
  for (const n of nodes) {
    const active = n.slug === current;
    const inPath = current === n.slug || (n.slug && current.startsWith(n.slug + '/'));
    out += `<li class="nav-item${n.children ? ' has-children' : ''}">`;
    out += `<a class="nav-link${active ? ' active' : ''}${inPath && !active ? ' in-path' : ''}" href="${href(n.slug)}">`;
    if (n.children) out += `<span class="nav-caret" aria-hidden="true"></span>`;
    else out += `<span class="nav-dot" aria-hidden="true"></span>`;
    out += `<span class="nav-text">${esc(n.short || n.title)}</span></a>`;
    if (n.children) out += renderNav(n.children, current, depth + 1);
    out += `</li>`;
  }
  return out + `</ul>`;
}

/* ---------- 상단 브레드크럼 ---------- */

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

/* ---------- 페이지 템플릿 ---------- */

function layout({ page, body, toc, prev, next }) {
  const crumbs = crumbsFor(page.slug);
  const crumbHtml = crumbs
    .map((c, i) =>
      i === crumbs.length - 1
        ? `<span aria-current="page">${esc(c.short || c.title)}</span>`
        : `<a href="${href(c.slug)}">${esc(c.short || c.title)}</a><span class="sep">/</span>`
    )
    .join('');

  const tocHtml = toc.length
    ? `<nav class="toc" aria-label="이 페이지 목차">
        <div class="toc-title">이 페이지 목차</div>
        <ul>${toc.map((t) => `<li class="toc-${t.tag}"><a href="#${t.id}">${esc(t.text)}</a></li>`).join('')}</ul>
      </nav>`
    : '';

  const pagerHtml = `<nav class="pager" aria-label="이전/다음 문서">
      ${prev ? `<a class="pager-link prev" href="${href(prev.slug)}"><span class="pager-dir">← 이전</span><span class="pager-title">${esc(prev.title)}</span></a>` : '<span></span>'}
      ${next ? `<a class="pager-link next" href="${href(next.slug)}"><span class="pager-dir">다음 →</span><span class="pager-title">${esc(next.title)}</span></a>` : '<span></span>'}
    </nav>`;

  const title = page.slug === '' ? site.title : `${page.title} · ${site.title}`;

  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(page.desc || site.description)}">
<meta property="og:title" content="${esc(page.title)}">
<meta property="og:description" content="${esc(page.desc || site.description)}">
<meta property="og:type" content="article">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/styles.css">
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
<a class="skip" href="#main">본문으로 건너뛰기</a>

<header class="topbar">
  <button class="icon-btn menu-btn" id="menuBtn" aria-label="문서 목록 열기" aria-expanded="false">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
  </button>
  <a class="brand" href="/">
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
      ${renderNav(tree, page.slug)}
    </div>
  </aside>
  <div class="sidebar-scrim" id="scrim" hidden></div>

  <main class="main" id="main">
    <article class="doc">
      <nav class="crumbs" aria-label="현재 위치">${crumbHtml}</nav>
      ${body}
      ${pagerHtml}
    </article>
    ${tocHtml}
  </main>
</div>

<footer class="footer">
  <span>메일파트 공용 메일 발송 서버(KMH) 문서 · 사내 참고용</span>
  <a class="dl" href="/mail-guide.html" download="메일발송서버 이용가이드.html">전체 문서 단일 HTML 내려받기 ↓</a>
</footer>

<script src="/app.js"></script>
</body>
</html>`;
}

/* ---------- 실행 ---------- */

async function copyDir(from, to) {
  await mkdir(to, { recursive: true });
  for (const entry of await readdir(from, { withFileTypes: true })) {
    const s = path.join(from, entry.name);
    const d = path.join(to, entry.name);
    if (entry.isDirectory()) await copyDir(s, d);
    else await copyFile(s, d);
  }
}

async function main() {
  if (existsSync(DIST)) await rm(DIST, { recursive: true });
  await mkdir(DIST, { recursive: true });
  if (existsSync(PUBLIC)) await copyDir(PUBLIC, DIST);

  const searchIndex = [];

  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    const raw = await readFile(path.join(CONTENT, page.file), 'utf8');
    const { html, toc } = processHeadings(raw);

    const out = layout({
      page,
      body: html,
      toc,
      prev: pages[i - 1],
      next: pages[i + 1],
    });

    const dir = page.slug ? path.join(DIST, page.slug) : DIST;
    await mkdir(dir, { recursive: true });
    await writeFile(path.join(dir, 'index.html'), out);

    searchIndex.push({
      t: page.title,
      u: href(page.slug),
      d: page.desc || '',
      h: toc.map((x) => x.text),
      // 본문 텍스트 (검색용, 태그 제거 후 압축)
      b: toText(html).slice(0, 4000),
    });

    console.log(`  ✓ ${href(page.slug) || '/'}`);
  }

  await writeFile(path.join(DIST, 'search-index.json'), JSON.stringify(searchIndex));
  console.log(`\n${pages.length}개 페이지 생성 완료 → dist/`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
