// ===================================
// Main Application
// ===================================

import { state } from './state.js';
import { api } from './api.js';
import Dashboard from './components/Dashboard.js';
import Chat from './components/Chat.js';

class App {
  constructor() {
    this.dashboard = null;
    this.chat = null;
  }

  // 앱 초기화
  async init() {
    console.log('🚀 K-WON Dashboard Initializing...');
    
    try {
      // 헬스 체크
      await this.checkHealth();
      
      // 컨테이너 생성
      this.createContainers();
      
      // 컴포넌트 초기화
      await this.initComponents();
      
      // 로딩 화면 제거
      this.hideLoadingScreen();
      
      console.log('✅ K-WON Dashboard Ready!');
    } catch (error) {
      console.error('❌ Initialization Error:', error);
      this.showError(error);
    }
  }

  // 헬스 체크
  async checkHealth() {
    try {
      const health = await api.checkHealth();
      state.set('isOnline', health.status === 'healthy');
      console.log('🏥 Backend Health:', health.status);
    } catch (error) {
      console.warn('⚠️ Backend connection failed, continuing anyway...');
      state.set('isOnline', false);
    }
  }

  // 컨테이너 생성
  createContainers() {
    const app = document.getElementById('app');
    app.innerHTML = `
      <div class="main-container">
        <div id="dashboardContainer"></div>
        <div id="chatContainer"></div>
      </div>
    `;
  }

  // 컴포넌트 초기화
  async initComponents() {
    // Dashboard 초기화
    const dashboardContainer = document.getElementById('dashboardContainer');
    this.dashboard = new Dashboard(dashboardContainer);
    await this.dashboard.init();
    
    // Chat 초기화
    const chatContainer = document.getElementById('chatContainer');
    this.chat = new Chat(chatContainer);
    this.chat.init();
    
    // 전역 참조 (액션 버튼에서 사용)
    window.dashboard = this.dashboard;
    window.chat = this.chat;
  }

  // 로딩 화면 제거
  hideLoadingScreen() {
    const loadingScreen = document.querySelector('.loading-screen');
    if (loadingScreen) {
      loadingScreen.classList.add('fade-out');
      setTimeout(() => {
        loadingScreen.remove();
      }, 300);
    }
  }

  // 에러 표시
  showError(error) {
    const app = document.getElementById('app');
    app.innerHTML = `
      <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        color: var(--text-primary);
        text-align: center;
        padding: 20px;
      ">
        <div style="font-size: 64px; margin-bottom: 20px;">⚠️</div>
        <h1 style="font-size: 24px; margin-bottom: 10px;">초기화 오류</h1>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">
          ${error.message || '알 수 없는 오류가 발생했습니다.'}
        </p>
        <button 
          onclick="location.reload()" 
          style="
            padding: 12px 24px;
            background: var(--primary-orange);
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 600;
          "
        >
          다시 시도
        </button>
      </div>
    `;
  }
}

// ===================================
// Bootstrap Application
// ===================================

document.addEventListener('DOMContentLoaded', () => {
  const app = new App();
  app.init();
});

// 전역 에러 핸들러
window.addEventListener('error', (event) => {
  console.error('Global Error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled Promise Rejection:', event.reason);
});