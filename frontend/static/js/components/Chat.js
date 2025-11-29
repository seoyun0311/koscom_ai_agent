// ===================================
// Chat Component (개선판)
// ===================================

import { state } from '../state.js';
import { api } from '../api.js';
import { CONFIG } from '../config.js';

class Chat {
  constructor(container) {
    this.container = container;
    this.messagesEl = null;
    this.inputEl = null;
    this.sendBtnEl = null;
    this.isProcessing = false;
  }

  init() {
    this.render();
    this.cacheElements();
    this.bindEvents();
    this.renderWelcomeMessage();
    this.subscribeToState();
  }

  // -----------------------------------
  // Render
  // -----------------------------------
  render() {
    this.container.innerHTML = `
      <div class="chat-panel">
        <div class="chat-header">
          <h2>💬 Claude AI</h2>
        </div>

        <div class="chat-messages" id="chatMessages"></div>

        <div class="chat-input-area">
          ${this.renderQuickActions()}
          <div class="chat-input-container">
            <textarea
              class="chat-input"
              id="chatInput"
              placeholder="질문을 입력하세요..."
              rows="1"
            ></textarea>
            <button class="chat-send-btn" id="sendBtn">SEND</button>
          </div>
        </div>
      </div>
    `;
  }

  renderQuickActions() {
    const actions = CONFIG.QUICK_ACTIONS || [];
    
    if (actions.length === 0) {
      return '<div class="quick-actions"></div>';
    }

    const buttons = actions.map(action => `
      <button class="quick-action-btn" data-query="${this.escapeHtml(action.query)}">
        ${this.escapeHtml(action.label)}
      </button>
    `).join('');

    return `<div class="quick-actions">${buttons}</div>`;
  }

  cacheElements() {
    this.messagesEl = this.container.querySelector('#chatMessages');
    this.inputEl = this.container.querySelector('#chatInput');
    this.sendBtnEl = this.container.querySelector('#sendBtn');
  }

  bindEvents() {
    // 빠른 질문 버튼
    this.container.querySelectorAll('.quick-action-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const query = btn.getAttribute('data-query');
        if (query) {
          this.sendMessage(query);
        }
      });
    });

    // Enter 전송 (Shift+Enter는 줄바꿈)
    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // Textarea 자동 높이 조정
    this.inputEl.addEventListener('input', () => {
      this.inputEl.style.height = 'auto';
      this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 120) + 'px';
    });

    // 버튼 클릭
    this.sendBtnEl.addEventListener('click', () => this.sendMessage());
  }

  subscribeToState() {
    // 메시지 상태 구독
    state.subscribe('messages', (messages) => {
      this.renderMessages(messages);
    });

    // 타이핑 상태 구독
    state.subscribe('isTyping', (isTyping) => {
      this.setLoading(isTyping);
    });
  }

  renderWelcomeMessage() {
    const text = [
      'K-WON 스테이블코인 모니터링 시스템입니다.',
      '',
      '<strong>자동 업데이트:</strong> 5초마다 실시간 갱신',
      '',
      '<strong>주요 기능:</strong>',
      '• 담보 비율 실시간 검증',
      '• 온/오프체인 데이터 분석',
      '• 종합 보고서 생성',
      '• 증빙 자료 패키지',
    ].join('<br />');

    this.addMessage(text, 'assistant');
  }

  renderMessages(messages) {
    if (!this.messagesEl) return;
    
    this.messagesEl.innerHTML = '';
    messages.forEach(msg => {
      const el = document.createElement('div');
      el.className = `message ${msg.type}`;
      el.innerHTML = this.formatMessage(msg.text);
      this.messagesEl.appendChild(el);
    });
    
    this.scrollToBottom();
  }

  // -----------------------------------
  // Message helpers
  // -----------------------------------
  addMessage(text, type = 'assistant') {
    state.addMessage(text, type);
  }

  formatMessage(text) {
    return String(text || '')
      .replace(/\n/g, '<br>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  }

  scrollToBottom() {
    if (this.messagesEl) {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
  }

  setLoading(isLoading) {
    if (isLoading) {
      this.sendBtnEl.disabled = true;
      this.sendBtnEl.textContent = '...';
      this.inputEl.disabled = true;
    } else {
      this.sendBtnEl.disabled = false;
      this.sendBtnEl.textContent = 'SEND';
      this.inputEl.disabled = false;
    }
  }

  // -----------------------------------
  // Send message
  // -----------------------------------
  async sendMessage(forcedText) {
    if (this.isProcessing) {
      console.log('⏳ 이미 처리 중입니다.');
      return;
    }

    const message = typeof forcedText === 'string'
      ? forcedText.trim()
      : this.inputEl.value.trim();

    if (!message) return;

    this.isProcessing = true;

    // 사용자 메시지 추가
    this.addMessage(message, 'user');

    // 입력창 초기화
    if (!forcedText) {
      this.inputEl.value = '';
      this.inputEl.style.height = '40px';
    }

    state.set('isTyping', true);

    try {
      const result = await api.sendChat(message);
      
      if (result.error) {
        throw new Error(result.error);
      }

      const answer = result?.response || '응답을 가져오지 못했습니다.';
      this.addMessage(answer, 'assistant');

      // 메타데이터 처리
      if (result?.metadata) {
        this.handleMetadata(result.metadata);
      }

    } catch (err) {
      console.error('Chat error:', err);
      
      let errorMessage = '⚠️ 오류가 발생했습니다.';
      
      if (err.message.includes('초과')) {
        errorMessage = '⏱️ 요청 시간이 초과되었습니다. 다시 시도해주세요.';
      } else if (err.message.includes('fetch')) {
        errorMessage = '🔌 서버와 연결할 수 없습니다. Flask 서버(http://localhost:5100)가 실행 중인지 확인하세요.';
      } else {
        errorMessage = `⚠️ ${err.message}`;
      }
      
      this.addMessage(errorMessage, 'assistant');
      
    } finally {
      state.set('isTyping', false);
      this.isProcessing = false;
    }
  }

  // -----------------------------------
  // 메타데이터 → state.activeVisualizations
  // -----------------------------------
  handleMetadata(metadata) {
    const visualizations = [];
    const hints = metadata.visualization_hints || [];
    const data = metadata.data_extracted || {};

    hints.forEach((hint) => {
      if (hint.type === 'bar_chart' && data.banks) {
        visualizations.push({
          type: 'bar_chart',
          title: hint.title || '은행별 익스포저',
          data: {
            labels: data.banks.map((b) => b.name),
            values: data.banks.map((b) => b.value),
          },
        });
      } else if (hint.type === 'status_card') {
        visualizations.push({
          type: 'status_card',
          title: hint.title || '정책 준수 현황',
          data: {
            status: metadata.policy_status || 'Unknown',
            description: hint.description || '',
          },
        });
      } else if (hint.type === 'gauge' && data.ratios?.length) {
        visualizations.push({
          type: 'gauge',
          title: hint.title || '담보 커버리지',
          data: { value: data.ratios[0] },
        });
      } else if (hint.type === 'risk_card') {
        visualizations.push({
          type: 'risk_card',
          title: hint.title || '리스크 평가',
          data: {
            level: metadata.risk_level || 'LOW',
            description: hint.description || '',
          },
        });
      }
    });

    if (visualizations.length > 0) {
      state.set('activeVisualizations', visualizations);
    }
  }

  // -----------------------------------
  // Utility
  // -----------------------------------
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

export default Chat;