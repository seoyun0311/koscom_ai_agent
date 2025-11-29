# K-WON Dynamic Dashboard

React 스타일 컴포넌트 구조의 원화 스테이블코인 모니터링 대시보드

## 🎨 주요 특징

### 디자인
- ✅ **세련된 UI**: 원본 디자인 100% 유지
- ✅ **동적 전환**: 챗 질문에 따라 실시간 시각화
- ✅ **반응형**: 모바일/태블릿/데스크톱 지원
- ✅ **애니메이션**: 부드러운 전환 효과

### 기능
- ✅ **실시간 모니터링**: 5초마다 자동 갱신
- ✅ **Claude AI 연동**: MCP Tools 22개 통합
- ✅ **동적 시각화**: Chart.js 기반 차트 생성
- ✅ **메타데이터 기반 렌더링**: 응답 분석 자동화

## 📁 프로젝트 구조

```
frontend/
├── templates/
│   └── index.html                 # 메인 HTML (최소 구조)
├── static/
│   ├── css/
│   │   ├── main.css              # 디자인 시스템 & 변수
│   │   ├── components.css        # 컴포넌트 스타일
│   │   └── animations.css        # 애니메이션
│   └── js/
│       ├── config.js             # 설정
│       ├── api.js                # API 통신
│       ├── state.js              # 상태 관리
│       ├── app.js                # 메인 앱
│       └── components/
│           ├── Dashboard.js      # 대시보드 컴포넌트
│           └── Chat.js           # 챗 컴포넌트
└── web_chat_app.py               # Flask 백엔드
```

## 🚀 설치 및 실행

### 1. 필수 요구사항

```bash
# Python 3.9+
python --version

# Node.js (백엔드 API 서버)
node --version
```

### 2. Python 패키지 설치

```bash
cd frontend
pip install flask anthropic python-dotenv requests
```

### 3. 환경 변수 설정

`.env` 파일 생성:

```env
ANTHROPIC_API_KEY=your_api_key_here
```

### 4. MCP 서버 실행

3개의 MCP 서버를 각각 실행:

```bash
# Terminal 1: Bank Monitoring MCP (포트 5300)
cd mcp_servers/bank_monitoring
python mcp_http_gateway.py

# Terminal 2: KRW Reserve MCP (포트 5400)
cd mcp_servers/krw-full-reserve
python mcp_http_gateway.py

# Terminal 3: KOSCOM Audit MCP (포트 5200)
cd mcp_servers/koscom_audit
python audit_gateway.py
```

### 5. 백엔드 API 서버 실행

```bash
# Terminal 4: Node.js Backend (포트 4000)
cd backend
npm start
```

### 6. Flask 앱 실행

```bash
# Terminal 5: Flask App (포트 5100)
cd frontend
python web_chat_app.py
```

### 7. 브라우저 접속

```
http://localhost:5100
```

## 🎯 사용 방법

### 기본 모니터링
- 대시보드가 자동으로 5초마다 갱신됩니다
- 온체인/오프체인/담보율 실시간 모니터링

### 동적 분석
1. 우측 채팅창에 질문 입력
2. Claude AI가 분석 수행
3. 관련 시각화 자동 생성

### 예시 질문

```
은행별 익스포저를 보여줘
정책 위반 현황은?
담보율을 분석해줘
리스크를 평가해줘
```

### 퀵 액션

- **은행 익스포저**: 은행별 예치금 분석
- **정책 위반**: 한도 위반 체크
- **담보율 분석**: 커버리지 분석
- **리스크 평가**: 종합 리스크 평가

## 📊 지원 시각화

### 자동 생성 시각화

1. **바 차트**: 은행별 익스포저 분포
2. **상태 카드**: 정책 준수 현황
3. **게이지**: 담보 커버리지 비율
4. **리스크 카드**: 위험도 평가
5. **테이블**: 상세 데이터 표시

## 🔧 아키텍처

### Frontend 구조

```javascript
// 상태 관리 (state.js)
State {
  metrics: {},          // 대시보드 데이터
  messages: [],         // 채팅 메시지
  mode: 'static',       // static/dynamic
  visualizations: []    // 활성 시각화
}

// 컴포넌트 (Dashboard.js, Chat.js)
Component {
  init()                // 초기화
  render()              // 렌더링
  setupListeners()      // 이벤트 리스너
}
```

### Backend 구조

```python
# Flask Routes
GET  /                          # 메인 페이지
GET  /api/health                # 헬스 체크
GET  /api/full-verification     # 대시보드 데이터
POST /api/chat                  # Claude AI 채팅
POST /api/reset                 # 대화 초기화

# Response Format
{
  "response": "...",            # AI 응답
  "metadata": {                 # 시각화 메타데이터
    "intent": [...],
    "data_extracted": {...},
    "tools_used": [...]
  }
}
```

## 🎨 디자인 시스템

### 색상

```css
--primary-orange: #ff6b35
--dark-bg: #0a0a0a
--card-bg: #161616
--success: #00e676
--warning: #ffa502
--danger: #ff4757
```

### 타이포그래피

```css
--font-family: Inter
--font-size-xs: 10px
--font-size-sm: 11px
--font-size-md: 13px
--font-size-lg: 16px
```

### 애니메이션

```css
--transition-fast: 0.15s ease
--transition-normal: 0.3s ease
--transition-slow: 0.5s ease
```

## 🔌 API 연동

### MCP Tools (22개)

#### KOSCOM Audit (10개)
- `events_recent`: 최근 거래 조회
- `event_proof`: 머클 증명
- `proof_pack`: 증빙 패키지
- 외 7개

#### Bank Monitoring (8개)
- `check_policy_compliance`: 정책 체크
- `bank_financials_by_name`: 재무제표
- `get_bank_risk_score`: 리스크 점수
- 외 5개

#### KRW Reserve (4개)
- `get_onchain_state`: 온체인 상태
- `check_coverage`: 담보율
- `get_risk_report`: 리스크 리포트
- 외 1개

## 🐛 트러블슈팅

### 포트 충돌
```bash
# 포트 사용 확인
lsof -i :5100
kill -9 <PID>
```

### MCP 서버 연결 실패
```bash
# 각 MCP 서버 로그 확인
# 5200, 5300, 5400 포트 확인
```

### 백엔드 연결 실패
```bash
# Node.js 백엔드 상태 확인
curl http://175.45.205.39:4000/status
```

## 📝 개발 가이드

### 새 시각화 추가

1. `components/Charts.js` 추가 (선택)
2. `components/Dashboard.js`의 `renderVisualization()` 수정
3. `components/Chat.js`의 `handleMetadata()` 수정

### 새 MCP Tool 추가

1. `web_chat_app.py`의 `CLAUDE_TOOLS` 배열에 추가
2. `execute_tool()` 함수에 라우팅 로직 추가

### 스타일 수정

- `static/css/main.css`: 변수 및 기본 스타일
- `static/css/components.css`: 컴포넌트 스타일
- `static/css/animations.css`: 애니메이션

## 📄 라이선스

MIT License

## 👥 기여

Issues 및 Pull Requests 환영합니다!

## 🙏 감사

- Anthropic Claude API
- Chart.js
- Flask
- Inter Font