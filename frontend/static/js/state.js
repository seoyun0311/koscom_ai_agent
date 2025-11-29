// ===================================
// State Management
// ===================================

import { CONFIG } from './config.js';

class StateManager {
  constructor() {
    this.state = {
      // Connection status
      isOnline: false,
      isLoading: false,
      
      // Dashboard mode
      mode: CONFIG.MODES.STATIC,
      
      // Dashboard data
      metrics: null,
      lastUpdate: null,
      
      // Chat state
      messages: [],
      isTyping: false,
      
      // Dynamic dashboard state
      activeVisualizations: [],
      highlightedCards: [],

      // Banks & FSS state
      banks: [],          // ← 역할 기반 분석 결과 등 은행 리스트 저장
      fssScores: {},      // ← bank_id → fss_score 매핑 저장
    };
    
    this.listeners = new Map();
  }

  // ------------------------------
  // Basic Get/Set
  // ------------------------------

  // Get state
  get(key) {
    return key ? this.state[key] : this.state;
  }

  // Set key/value and notify listeners
  set(key, value) {
    const oldValue = this.state[key];
    this.state[key] = value;
    this.notify(key, value, oldValue);
  }

  // Update multiple values
  update(updates) {
    Object.entries(updates).forEach(([key, value]) => {
      this.set(key, value);
    });
  }

  // ------------------------------
  // Pub/Sub
  // ------------------------------

  subscribe(key, callback) {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, []);
    }
    this.listeners.get(key).push(callback);

    // Unsubscribe method
    return () => {
      const arr = this.listeners.get(key);
      const idx = arr.indexOf(callback);
      if (idx > -1) arr.splice(idx, 1);
    };
  }

  notify(key, newValue, oldValue) {
    const list = this.listeners.get(key);
    if (list) {
      list.forEach(cb => cb(newValue, oldValue));
    }

    // wildcard listeners for all state keys
    const wildcard = this.listeners.get('*');
    if (wildcard) {
      wildcard.forEach(cb => cb(key, newValue, oldValue));
    }
  }

  // ------------------------------
  // Chat state
  // ------------------------------

  addMessage(text, type) {
    const message = {
      id: Date.now(),
      text,
      type, 
      timestamp: new Date()
    };

    this.state.messages.push(message);
    this.notify('messages', this.state.messages);

    return message;
  }

  clearMessages() {
    this.state.messages = [];
    this.notify('messages', this.state.messages);
  }

  // ------------------------------
  // Dashboard / UI states
  // ------------------------------

  setMode(mode) {
    if (Object.values(CONFIG.MODES).includes(mode)) {
      this.set('mode', mode);
    }
  }

  addVisualization(viz) {
    this.state.activeVisualizations.push(viz);
    this.notify('activeVisualizations', this.state.activeVisualizations);
  }

  clearVisualizations() {
    this.state.activeVisualizations = [];
    this.notify('activeVisualizations', this.state.activeVisualizations);
  }

  highlightCards(cardIds) {
    this.set('highlightedCards', cardIds);
  }

  clearHighlights() {
    this.set('highlightedCards', []);
  }

  // ==============================================
  //  FSS Scores & Bank List Management (추가됨)
  // ==============================================

  /**
   * Save computed FSS score for a single bank
   */
  setFSS(bank_id, score) {
    this.state.fssScores[bank_id] = score;
    this.notify('fssScores', this.state.fssScores);
  }

  /**
   * Replace the whole banks list (e.g. role_based_allocation result)
   */
  setBanks(banks) {
    this.state.banks = banks;
    this.notify('banks', this.state.banks);
  }

  /**
   * After role_based_allocation, merge fssScores into bank objects for UI
   */
  updateBankFSS(banks) {
    this.state.banks = banks.map(b => {
      const savedScore = this.state.fssScores[b.bank_id];
      return {
        ...b,
        fss: savedScore !== undefined ? savedScore : b.fss
      };
    });

    this.notify('banks', this.state.banks);
  }
}

// Singleton instance
export const state = new StateManager();
export default state;
