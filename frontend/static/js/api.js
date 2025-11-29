// ===================================
// API Communication Module (최종 개선판)
// ===================================

import { CONFIG } from './config.js';

export class API {
  constructor() {
    this.baseURL = CONFIG.API_BASE;
    this.timeout = 30000; // 30초 타임아웃
  }

  // ---------------------------------------------------
  // Generic fetch wrapper (timeout + error handling)
  // ---------------------------------------------------
  async fetch(endpoint, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseURL}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        },
        signal: controller.signal,
        ...options
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();

    } catch (error) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError') {
        throw new Error('요청 시간이 초과되었습니다. 다시 시도해주세요.');
      }

      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    }
  }

  // ---------------------------------------------------
  // System APIs
  // ---------------------------------------------------

  async checkHealth() {
    try {
      return await this.fetch('/health');
    } catch (error) {
      return { status: 'unhealthy', error: error.message };
    }
  }

  async getFullVerification() {
    return this.fetch('/full-verification');
  }

  async sendChat(message) {
    return this.fetch('/chat', {
      method: 'POST',
      body: JSON.stringify({ message })
    });
  }

  async resetConversation() {
    return this.fetch('/reset', {
      method: 'POST'
    });
  }

  // ===================================
  // MCP Tools 호출 API
  // ===================================

  /**
   * FSS 점수 계산 MCP 호출
   * params = {
   *   bank_id,
   *   name,
   *   score_income,
   *   score_capital,
   *   score_liquidity,
   *   score_asset,
   *   ...etc
   * }
   */
  async computeFSS(params) {
    return this.fetch('/mcp', {
      method: 'POST',
      body: JSON.stringify({
        tool: "compute_fss_for_bank",
        params
      })
    });
  }

  /**
   * 역할 기반 비중 계산 MCP 호출
   * institutions = [
   *   { bank_id, name, exposure, fss, role }
   * ]
   */
  async roleBasedAllocation(institutions) {
    return this.fetch('/mcp', {
      method: 'POST',
      body: JSON.stringify({
        tool: "role_based_allocation",
        params: { institutions }
      })
    });
  }
}

// Singleton instance
export const api = new API();
export default api;
