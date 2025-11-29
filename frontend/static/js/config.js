// static/js/config.js

// 전역 설정 값
export const CONFIG = {
    // Flask 백엔드 API 베이스 URL
    API_BASE: 'http://localhost:5100/api',
  
    // 대시보드 자동 새로고침 주기 (ms)
    REFRESH_INTERVAL: 5000,
  
    // 대시보드 모드
    MODES: {
      STATIC: 'STATIC',
      DYNAMIC: 'DYNAMIC',
    },
  
    // 우측 채팅창 상단의 퀵 액션 버튼들
    // Chat.js 의 renderQuickActions() 에서 사용됨
    QUICK_ACTIONS: [
      {
        label: '담보 분석',
        query: '지금 KRWS 담보 구조와 커버리지 리스크를 분석해줘.',
      },
      {
        label: '보고서',
        query:
          '오늘 기준 K-WON 스테이블코인 전체 검증 리포트를 자세히 써줘. ' +
          '온체인 공급, 오프체인 준비금, 커버리지 비율, 리스크 요인까지 정리해줘.',
      },
      {
        label: '증빙팩',
        query:
          '가장 최근 거래에 대한 온체인/오프체인 증빙팩을 생성하는 전체 프로세스를 설명해줘.',
      },
      {
        label: '은행 리스크',
        query:
          '각 수탁기관(은행)의 익스포저, 커버리지, 리스크 수준을 평가하고 ' +
          '한도 여유/집중도 이슈를 알려줘.',
      },
    ],
  };
  
  // 기본 export 도 같이 제공 (import CONFIG from ... 형태로도 쓸 수 있게)
  export default CONFIG;
  