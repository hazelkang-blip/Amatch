// 문서 트리 구조 — 원본 위키의 목차/하위 페이지 구조를 그대로 반영
export const site = {
  title: '메일발송서버 이용가이드',
  description: '메일파트에서 제공하는 공용 메일 발송 서버(KMH) 이용 가이드',
};

export const tree = [
  {
    slug: '',
    file: 'index.html',
    title: '메일발송서버 이용가이드',
    short: '메일발송서버 이용가이드',
    desc: '공용 메일 발송 서버 개요, 주의사항, 발송 방법, SPF/DKIM/DMARC 설정',
    children: [
      {
        slug: 'dkim',
        file: 'dkim.html',
        title: 'DKIM 설정 가이드',
        desc: 'DKIM 개념, DKIM-Signature 구조와 설정 작업 순서',
      },
      {
        slug: 'kmh-send-result-api',
        file: 'kmh-send-result-api.html',
        title: 'KMH 발송결과확인 API',
        desc: '발송 로그 조회 API 접속 정보, 파라미터, 응답 규격',
      },
      {
        slug: 'c',
        file: 'c.html',
        title: '메일발송서버 이용가이드 - c',
        short: 'c',
        desc: 'C 언어에서 메일 발송하기',
        children: [
          { slug: 'c/hm-libs-smtp', file: 'c-hm-libs-smtp.html', title: 'c hm libs 로 smtp 구현', desc: 'hm_mail 라이브러리로 SMTP 클라이언트 직접 구현' },
          { slug: 'c/libcurl-smtp', file: 'c-libcurl-smtp.html', title: 'libcurl smtp', desc: 'libcurl 의 SMTP 지원을 이용한 메일 발송' },
        ],
      },
      {
        slug: 'java',
        file: 'java.html',
        title: '메일발송서버 이용가이드 - java',
        short: 'java',
        desc: 'Java 에서 메일 발송하기 (Spring, Commons Email, JavaMail)',
        children: [
          { slug: 'java/apache-commons-email', file: 'java-apache-commons-email.html', title: 'Apache Commons Email', desc: 'Commons Email 로 일반/첨부 메일 발송' },
          { slug: 'java/dkim', file: 'java-dkim.html', title: 'java - DKIM 붙여서 메일 발송 하기', desc: 'Java 에서 DKIM 서명을 붙여 발송' },
          { slug: 'java/legacy-version-guide', file: 'java-legacy-version-guide.html', title: '다른버전 이용자를 위한 가이드', desc: '구 버전 daum_mail 라이브러리에서 마이그레이션' },
        ],
      },
      { slug: 'perl', file: 'perl.html', title: '메일발송서버 이용가이드 - perl language', short: 'perl language', desc: 'Net::SMTP, Mail::Send, MIME::Lite 예제' },
      { slug: 'python', file: 'python.html', title: '메일발송서버 이용가이드 - python', short: 'python', desc: 'smtplib / MIMEText 예제와 인코딩 이슈' },
      { slug: 'r', file: 'r.html', title: '메일발송서버 이용가이드 - R', short: 'R', desc: 'mailR 패키지를 이용한 발송' },
      { slug: 'ruby', file: 'ruby.html', title: '메일발송서버 이용가이드 - ruby language', short: 'ruby language', desc: 'Net::SMTP 를 이용한 발송' },
      { slug: 'shell', file: 'shell.html', title: '메일발송서버 이용가이드 - shell', short: 'shell', desc: 'telnet 으로 SMTP 세션 직접 주고받기' },
      { slug: 'one-click-unsubscribe', file: 'one-click-unsubscribe.html', title: '원클릭 수신거부 설정 가이드', desc: 'Gmail 발신자 가이드라인 대응 원클릭 수신거부' },
    ],
  },
];

// 트리를 평탄화 (이전/다음 네비게이션 및 검색용)
export function flatten(nodes = tree, depth = 0, out = []) {
  for (const n of nodes) {
    out.push({ ...n, depth });
    if (n.children) flatten(n.children, depth + 1, out);
  }
  return out;
}
