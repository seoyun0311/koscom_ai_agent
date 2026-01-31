# 💱 원화 스테이블 코인 리스크 관리 AI AGENT

> **KOSCOM AI Agent Challenge 2025**
> 원화 스테이블코인 발행·운영 환경을 위한 **실시간 리스크 관리·감사 자동화 AI Agent 시스템**

본 프로젝트는 원화 스테이블코인 도입이 가속화되는 환경에서,
발행사가 직면하는 **준비금 검증, 예치은행 신용위험, 감사·규제 대응 문제**를
**MCP(Multi-Component Process) 기반 AI Agent**로 해결하는 것을 목표로 합니다.

---
## 🧑‍💻 Team DANCOM
|  권민석  |  김도연  |  양서윤  |  이도원  | 
| :-----: | :-----: | :-----: | :-----: | 
| <img src="https://avatars.githubusercontent.com/u/155413606?v=4" width=150px alt="권민석"> | <img src="https://avatars.githubusercontent.com/u/186993697?v=4" width=150px alt="김도연"> | <img src="https://avatars.githubusercontent.com/u/138513591?v=4" width=150px alt="양서윤"> | <img src="https://avatars.githubusercontent.com/u/204447212?v=4" width=150px alt="이도원"> | 
| [@kwonminseok242](https://github.com/kwonminseok242) | [@kxmdoyn](https://github.com/kxmdoyn) | [@seoyun0311](https://github.com/seoyun0311) | [@leedw21](https://github.com/leedw21) |

---

## 1️⃣ 기획 배경 및 목적

### 왜 원화 스테이블코인인가?

* 글로벌 스테이블코인 시장의 급격한 성장
* 디지털 달러 패권 경쟁 심화
* 한국 통화 주권 및 디지털 지급결제 경쟁력 확보 필요

과거 Terra/Luna, Tether 사례에서 드러났듯이
**준비금 불투명성·감사 부재·신뢰 붕괴**는 시스템 리스크로 직결됩니다.

👉 **원화 스테이블코인의 핵심은 ‘기술’이 아니라 ‘신뢰’이며, 이는 실시간 리스크 관리 체계 없이는 불가능**합니다.

---

## 2️⃣ 발행사의 4대 Pain Point

1. **준비금 실시간 검증 불가**

   * 온·오프체인 데이터 단절
   * 은행 조회 지연 및 수작업 검증

2. **예치은행 신용·집중 위험**

   * 특정 은행 리스크가 전체 시스템 리스크로 전이

3. **감사 추적 및 불변 기록 한계**

   * 내부 DB 변경 가능성
   * 규제기관 신뢰 확보 어려움

4. **규제 보고·감사 대응 부담**

   * AML/STR 등 수작업 보고의 한계

---

## 3️⃣ 해결 전략 : MCP 기반 AI Agent

발행사의 로컬 스테이블코인 운영 환경을 유지하면서,
리스크 관리 영역만 **클라우드 + MCP 서버 + AI Agent**로 분리합니다.

### AI Agent의 역할

* 실시간 담보 비율 검증
* 예치은행 신용위험 점수화
* 정책 기반 분산·재배치 제안
* 감사·규제 보고 자동 생성

---

## 4️⃣ 전체 아키텍처 개요

```text
[ Local Stablecoin System ]
        ↓ (API / Event)
[ Cloud DB (PostgreSQL) ]
        ↓
[ MCP Servers ]  ←→  [ AI Risk Agent (Claude) ]
        ↓
[ K-WON Dashboard / Evidence / Report ]
```

* **발행 시스템은 변경 최소화**
* 리스크 분석·감사·보고만 외부에서 독립 수행
* MCP 서버는 표준 HTTP 인터페이스로 확장 가능

---

## 5️⃣ MCP Server 구성 (핵심 요약)

```bash
mcp_servers/
├── bank_monitering/     # 예치은행 신용위험 & 분산도 관리
├── krw-full-reserve/   # 1:1 완전 담보 실시간 검증
├── tx_audit/           # 실시간 감사 추적 & 불변 증빙 생성
└── report-master/      # 규제 준수 보고 자동화
```

---

### 🛡 MCP SERVER ① : 1:1 완전 담보 실시간 검증

* 온체인 발행량 vs 오프체인 준비금 실시간 비교
* 담보 비율(Coverage Ratio) 계산
* 상태 구간 정의

  * 🟢 안전 : 115% 이상
  * 🟡 주의 : 103~115%
  * 🔴 위험 : 103% 미만

---

### 🏦 MCP SERVER ② : 예치은행 신용위험 & 분산도 관리

* 은행 재무 데이터(DART/FSS) 연동
* 신용등급·CDS 기반 Risk Score 산출
* 집중도(HHI) 및 내부 정책 자동 검증
* 재배치 시나리오 제안

---

### 🔎 MCP SERVER ③ : 감사 추적 & 불변 기록

* 체인 이벤트 수집 및 Merkle 기반 증빙 생성
* 감사용 Evidence Package 자동 생성
* 데이터 무결성 및 추적 가능성 확보

---

### 📑 MCP SERVER ④ : 컴플라이언스 리포트 자동화

* 실시간 리스크 요약
* 월간/분기 규제 보고서 자동 생성
* AI 자연어 요약을 통한 감독기관 대응

---

## 6️⃣ K-WON 운영 대시보드

* On-chain Supply / Net Circulation
* Off-chain Reserves (은행별 분포)
* 담보 비율 및 초과 담보
* AI Agent 대화형 질의
* Evidence & Report 즉시 생성

---

