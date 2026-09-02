# 메일발송서버 이용가이드 (웹 배포판)

사내 위키 PDF 16개를 웹 문서 사이트로 변환한 정적 사이트입니다.
빌드 의존성이 전혀 없습니다 (Node 18+ 표준 라이브러리만 사용).

## 구조

```
mail-guide/
├── nav.mjs            # 문서 트리(목차/하위 페이지 구조) — 여기만 고치면 사이드바가 바뀜
├── content/*.html     # 페이지별 본문 조각 (h1 + 본문)
├── public/            # styles.css, app.js, favicon.svg — 그대로 dist 로 복사됨
├── build.mjs          # 멀티 페이지 사이트 생성 (17개 HTML)
├── build-single.mjs   # 전체 문서를 담은 단일 HTML 파일 생성
├── serve.mjs          # 로컬 미리보기 서버
└── dist/              # 빌드 결과 (git 무시)
    ├── index.html …   #   멀티 페이지 사이트
    └── mail-guide.html #  단일 HTML 배포판
```

## 문서 트리

| 경로 | 문서 |
| --- | --- |
| `/` | 메일발송서버 이용가이드 |
| `/dkim` | DKIM 설정 가이드 |
| `/kmh-send-result-api` | KMH 발송결과확인 API |
| `/c` | 메일발송서버 이용가이드 - c |
| `/c/hm-libs-smtp` | └ c hm libs 로 smtp 구현 |
| `/c/libcurl-smtp` | └ libcurl smtp |
| `/java` | 메일발송서버 이용가이드 - java |
| `/java/apache-commons-email` | └ Apache Commons Email |
| `/java/dkim` | └ java - DKIM 붙여서 메일 발송 하기 |
| `/java/legacy-version-guide` | └ 다른버전 이용자를 위한 가이드 |
| `/perl` | 메일발송서버 이용가이드 - perl language |
| `/python` | 메일발송서버 이용가이드 - python |
| `/r` | 메일발송서버 이용가이드 - R |
| `/ruby` | 메일발송서버 이용가이드 - ruby language |
| `/shell` | 메일발송서버 이용가이드 - shell |
| `/one-click-unsubscribe` | 원클릭 수신거부 설정 가이드 |

## 빌드 산출물 두 가지

| 산출물 | 용도 |
| --- | --- |
| `dist/` 전체 | Vercel 등에 올리는 멀티 페이지 사이트 |
| `dist/mail-guide.html` | **단일 HTML 배포판** — 파일 하나만 전달/다운로드 |

### 단일 HTML 배포판

- 17개 문서 전체 + CSS + JS + 아이콘이 **한 파일에 인라인**되어 있습니다. 외부 요청 0건.
- 서버 없이 `file://` 로 열어도, 사내망이 끊긴 노트북에서도 그대로 동작합니다.
- 사이드바 트리, 페이지 내 목차, 다크모드, 코드 복사, 문서 검색까지 전부 유지됩니다.
  (검색 인덱스도 파일 안에 들어 있어 오프라인에서 동작)
- 페이지 이동은 해시 라우팅(`mail-guide.html#/python`)이라 특정 문서로 바로 링크할 수 있습니다.
- 브라우저에서 **인쇄(⌘P / Ctrl+P)** 하면 17개 문서가 이어진 한 권으로 출력·PDF 저장됩니다.
- 현재 용량 약 206 KB.

## 로컬 실행

```bash
npm run build && node serve.mjs
```

`http://localhost:4321` (사이트) / `http://localhost:4321/mail-guide.html` (단일 파일) 로 접속합니다.

| 명령 | 동작 |
| --- | --- |
| `npm run build` | 사이트 + 단일 HTML 모두 생성 |
| `npm run build:site` | 멀티 페이지 사이트만 |
| `npm run build:single` | 단일 HTML 만 |

## Vercel 배포

이 디렉터리가 **프로젝트 루트**가 되어야 합니다 (저장소 루트의 `vercel.json` 은 별개의 Python API 설정).

```bash
cd mail-guide && npx vercel
```

- 처음 실행하면 프로젝트 이름을 물어보고, 이 디렉터리를 루트로 잡은 새 프로젝트가 생성됩니다.
- 운영 배포는 `npx vercel --prod`.
- GitHub 연동으로 배포할 경우 Vercel 대시보드에서 **Settings → General → Root Directory** 를 `mail-guide` 로 지정하세요.

`vercel.json` 설정:

| 항목 | 값 |
| --- | --- |
| `buildCommand` | `node build.mjs && node build-single.mjs` |
| `outputDirectory` | `dist` |
| `installCommand` | 없음 (의존성 없음) |
| `cleanUrls` | `true` — `/python.html` 대신 `/python` |

배포 후 사이트 푸터의 **“전체 문서 단일 HTML 내려받기”** 링크로 `mail-guide.html` 을 받을 수 있습니다.

## 내용 수정 방법

- **본문 수정**: `content/<파일>.html` 을 고친 뒤 `npm run build` (두 산출물이 같은 원본을 공유합니다)
- **페이지 추가/구조 변경**: `nav.mjs` 의 `tree` 에 항목을 추가하고 같은 이름의 `content/*.html` 생성
- `h2` / `h3` 에는 빌드 시 자동으로 앵커 id 와 우측 "이 페이지 목차" 항목이 붙습니다.
  고정 앵커가 필요하면 `<h2 id="my-id">` 처럼 직접 지정하세요.
- 코드 블록은 `<div class="codeblock"><div class="codeblock-head">…</div><pre><code>…</code></pre></div>`
  형태로 작성하면 복사 버튼이 자동으로 붙습니다.

## 참고 사항

- 원본 위키 목차에 있던 `(deprecated) daum-mail library` 는 원본 PDF 가 없어 제외했습니다.
  나중에 추가하려면 `nav.mjs` 의 `java` 하위에 항목을 넣고 같은 이름의 `content/*.html` 을 만들면 됩니다.
- 문서에 사내 호스트명·아지트 링크·DKIM 셀렉터 등 내부 정보가 포함되어 있습니다.
  공개 URL 로 열어두지 말고 Vercel 의 **Deployment Protection**(Vercel Authentication 또는 Password Protection)을
  켜두는 것을 권장합니다.
