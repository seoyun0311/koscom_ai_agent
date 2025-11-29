// ===================================
// Dashboard Component
// ===================================

import { state } from '../state.js';
import { api } from '../api.js';
import { CONFIG } from '../config.js';

export class Dashboard {
  constructor(container) {
    this.container = container;
    this.refreshInterval = null;
    this.isFirstLoad = true;
  }

  // -----------------------------------
  // 초기화
  // -----------------------------------
  async init() {
    this.render();
    this.setupSubscriptions();
    this.setupActions();

    // 초기 상태 반영
    this.updateConnectionStatus(state.get('isOnline'));
    this.updateMode(state.get('mode'));

    // 첫 데이터 로드 + 주기적 갱신
    await this.refreshMetrics();
    this.startAutoRefresh();
  }

  // -----------------------------------
  // 렌더링
  // -----------------------------------
  render() {
    this.container.innerHTML = `
      <div class="dashboard-panel">
        <div class="dashboard-content">
          ${this.renderHeader()}
          ${this.renderLoadingIndicator()}
          ${this.renderMainGrid()}
          ${this.renderDynamicArea()}
          ${this.renderActionButtons()}
        </div>
      </div>
    `;
  }

  renderHeader() {
    return `
      <div class="dashboard-header">
        <div class="logo-section">
          <div class="logo-icon">₩</div>
          <div class="logo-text">
            <h1>K-WON STABLECOIN DASHBOARD</h1>
          </div>
        </div>
        <div class="status-indicator">
          <div class="status-dot" id="statusDot"></div>
          <span class="status-text" id="statusText">Offline</span>
        </div>
      </div>
    `;
  }

  renderLoadingIndicator() {
    return `
      <div class="loading-indicator" id="loadingIndicator">
        <span class="loading-spinner"></span>
        <span style="font-size: 11px; text-transform: uppercase;">
          Loading Data...
        </span>
      </div>
    `;
  }

  renderMainGrid() {
    return `
      <div class="content-grid" id="mainContentGrid">
        <!-- Top Left: OnChain Supply -->
        <div class="content-card" id="card-onchain">
          <div class="card-header">
            <div class="card-title-section">
              <span class="card-icon">🔗</span>
              <span class="card-title">On-Chain Supply</span>
            </div>
          </div>

          <div class="data-row">
            <div class="data-label">Total Supply</div>
            <div class="data-value" id="totalSupplyMain">-</div>
            <div class="data-subtitle">Blockchain Tokens</div>
          </div>

          <div class="data-row">
            <div class="data-label">Net Circulation</div>
            <div class="data-value" id="netCirculationMain">-</div>
            <div class="data-subtitle">Active Tokens</div>
          </div>

          <div class="data-row">
            <div class="data-label">Burned</div>
            <div class="data-value" id="burnedMain">-</div>
            <div class="data-subtitle">Destroyed Tokens</div>
          </div>

          <div class="timestamp" id="onchainTimestamp">-</div>
        </div>

        <!-- Right: OffChain Reserves (Spans 2 rows) -->
        <div class="content-card offchain-card" id="card-offchain">
          <div class="card-header">
            <div class="card-title-section">
              <span class="card-icon">🏦</span>
              <span class="card-title">Off-Chain Reserves</span>
            </div>
          </div>

          <div
            style="
              padding: 28px 24px;
              background: rgba(255, 107, 53, 0.08);
              border: 1px solid rgba(255, 107, 53, 0.3);
              margin-bottom: 20px;
              flex-shrink: 0;
            "
          >
            <div class="data-label" style="font-size: 12px">
              Total Reserves
            </div>
            <div
              class="card-value"
              id="totalReservesMain"
              style="font-size: 42px; margin: 8px 0"
            >
              -
            </div>
            <div class="data-subtitle" style="font-size: 12px">
              Financial Institutions
            </div>
          </div>

          <!-- Custodian List -->
          <div style="overflow-y: auto; flex: 1">
            <ul class="custodian-list" id="custodianList">
              <!-- Populated dynamically -->
            </ul>
          </div>

          <div class="timestamp" id="offchainTimestamp">-</div>
        </div>

        <!-- Bottom Left: Collateral Ratio -->
        <div class="content-card" id="card-coverage">
          <div class="card-header">
            <div class="card-title-section">
              <span class="card-icon">📊</span>
              <span class="card-title">Collateral Ratio</span>
            </div>
          </div>

          <div
            style="
              padding: 32px 28px;
              background: rgba(255, 107, 53, 0.08);
              border: 1px solid rgba(255, 107, 53, 0.3);
              margin-bottom: 20px;
              flex-shrink: 0;
            "
          >
            <div
              class="data-label"
              style="margin-bottom: 14px; font-size: 12px"
            >
              Coverage Ratio
            </div>
            <div
              style="
                display: flex;
                align-items: baseline;
                gap: 8px;
                margin-bottom: 24px;
              "
            >
              <span
                class="card-value"
                id="coverageRatioMain"
                style="font-size: 56px"
              >-</span>
              <span
                style="
                  font-size: 32px;
                  color: var(--text-secondary);
                  font-weight: 700;
                "
              >%</span>
            </div>
            <div class="coverage-bar" style="margin-bottom: 14px">
              <div
                class="coverage-fill"
                id="coverageFillMain"
                style="width: 0%"
              ></div>
            </div>
            <div
              style="
                font-size: 11px;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.8px;
                line-height: 1.6;
              "
            >
              Target: 105% Min • Status:
              <span
                id="coverageStatus"
                style="font-weight: 700; color: var(--text-primary)"
              >-</span>
            </div>
          </div>

          <div class="data-row" style="flex-shrink: 0">
            <div class="data-label">Excess Collateral</div>
            <div
              class="data-value"
              id="excessCollateral"
              style="font-size: 24px"
            >
              -
            </div>
            <div class="data-subtitle">Safety Buffer</div>
          </div>

          <div class="timestamp" id="collateralTimestamp">-</div>
        </div>
      </div>
    `;
  }

  // 동적 시각화 영역
  renderDynamicArea() {
    return `
      <div id="dynamicVisualizations" style="margin: 24px 0;">
        <!-- Chat 메타데이터 기반 동적 위젯들이 들어가는 영역 -->
      </div>
    `;
  }

  // 하단 액션 버튼
  renderActionButtons() {
    return `
      <div class="action-buttons">
        <div class="action-card-compact" id="btnGenerateReport">
          <div class="action-icon-compact">📊</div>
          <div class="action-content">
            <div class="action-title-compact">Report</div>
            <div class="action-description-compact">
              Full verification report with analysis
            </div>
          </div>
          <button class="action-button-small">Generate</button>
        </div>

        <div class="action-card-compact" id="btnGenerateEvidence">
          <div class="action-icon-compact">📦</div>
          <div class="action-content">
            <div class="action-title-compact">Evidence</div>
            <div class="action-description-compact">
              Audit package with transaction logs
            </div>
          </div>
          <button class="action-button-small">Generate</button>
        </div>
      </div>
    `;
  }

  // -----------------------------------
  // 상태 구독
  // -----------------------------------
  setupSubscriptions() {
    // 백엔드 연결 상태
    state.subscribe('isOnline', (isOnline) => {
      this.updateConnectionStatus(isOnline);
    });

    // 로딩 상태
    state.subscribe('isLoading', (isLoading) => {
      this.updateLoadingIndicator(isLoading);
    });

    // 메트릭 데이터
    state.subscribe('metrics', (metrics) => {
      if (metrics) this.updateMetrics(metrics);
    });

    // 모드 (STATIC / DYNAMIC)
    state.subscribe('mode', (mode) => {
      this.updateMode(mode);
    });

    // 동적 시각화
    state.subscribe('activeVisualizations', (visualizations) => {
      this.renderVisualizations(visualizations || []);
    });
  }

  // -----------------------------------
  // 액션 버튼 핸들러
  // -----------------------------------
  setupActions() {
    const reportBtn = this.container.querySelector('#btnGenerateReport');
    const evidenceBtn = this.container.querySelector('#btnGenerateEvidence');

    if (reportBtn) {
      reportBtn.addEventListener('click', () => {
        if (window.chat && typeof window.chat.sendMessage === 'function') {
          window.chat.sendMessage('K-WON 담보 구조 전체에 대한 검증 보고서를 만들어줘.');
        }
      });
    }

    if (evidenceBtn) {
      evidenceBtn.addEventListener('click', () => {
        if (window.chat && typeof window.chat.sendMessage === 'function') {
          window.chat.sendMessage('특정 거래에 대한 온체인/오프체인 증빙팩을 생성하는 방법을 안내해줘.');
        }
      });
    }
  }

  // -----------------------------------
  // 주기적 갱신
  // -----------------------------------
  startAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }

    this.refreshInterval = setInterval(() => {
      this.refreshMetrics();
    }, 5000);
  }

  async refreshMetrics() {
    try {
  
      // ✅ 최초 로딩 때만 로딩 표시
      if (this.isFirstLoad) {
        state.set('isLoading', true);
      }
  
      const result = await api.getFullVerification();
  
      if (result && result.success) {
        state.set('metrics', result.data);
        state.set('lastUpdate', new Date());
      }
  
    } catch (error) {
      console.error('Dashboard refresh error:', error);
    } finally {
  
      if (this.isFirstLoad) {
        state.set('isLoading', false);
        this.isFirstLoad = false; // ✅ 이후 갱신은 로딩 표시 안 함
      }
  
    }
  }
  

  // -----------------------------------
  // 상태 업데이트 helpers
  // -----------------------------------
  updateConnectionStatus(isOnline) {
    const statusDot = this.container.querySelector('#statusDot');
    const statusText = this.container.querySelector('#statusText');
    if (!statusDot || !statusText) return;

    if (isOnline) {
      statusDot.style.background = 'var(--success)';
      statusText.textContent = 'Online';
    } else {
      statusDot.style.background = 'var(--danger)';
      statusText.textContent = 'Offline';
    }
  }

  updateLoadingIndicator(isLoading) {
    const el = this.container.querySelector('#loadingIndicator');
    if (!el) return;
    if (isLoading) {
      el.classList.add('active');
    } else {
      el.classList.remove('active');
    }
  }

  updateMode(mode) {
    const grid = this.container.querySelector('#mainContentGrid');
    if (!grid) return;

    if (mode === CONFIG.MODES.DYNAMIC) {
      grid.classList.add('dynamic-mode');
    } else {
      grid.classList.remove('dynamic-mode');
    }
  }

  // -----------------------------------
  // 메트릭 반영 (기존 index.html 로직 포팅)
  // -----------------------------------
  updateMetrics(data) {
    if (!data) return;

    const ratio = data.coverage.coverage_ratio;

    // 숫자 포맷터
    const formatNumber = (num) =>
      new Intl.NumberFormat('ko-KR').format(num);
    const formatKRW = (num) => '₩' + formatNumber(num);

    // OnChain
    const totalSupplyEl = this.container.querySelector('#totalSupplyMain');
    const netCircEl = this.container.querySelector('#netCirculationMain');
    const burnedEl = this.container.querySelector('#burnedMain');
    const onchainTsEl = this.container.querySelector('#onchainTimestamp');

    if (totalSupplyEl) totalSupplyEl.textContent = formatKRW(data.onchain.total_supply);
    if (netCircEl) netCircEl.textContent = formatKRW(data.onchain.net_circulation);
    if (burnedEl) burnedEl.textContent = formatKRW(data.onchain.burned);
    if (onchainTsEl) {
      onchainTsEl.textContent = new Date(data.onchain.timestamp).toLocaleString('ko-KR');
    }

    // Coverage Ratio
    const ratioEl = this.container.querySelector('#coverageRatioMain');
    const coverageFillEl = this.container.querySelector('#coverageFillMain');
    const coverageStatusEl = this.container.querySelector('#coverageStatus');
    const excessEl = this.container.querySelector('#excessCollateral');
    const collateralTsEl = this.container.querySelector('#collateralTimestamp');

    if (ratioEl) {
      ratioEl.textContent = ratio;
      ratioEl.className =
        'card-value ' +
        (ratio >= 105
          ? 'value-ok'
          : ratio >= 100
          ? 'value-warning'
          : 'value-danger');
    }

    if (coverageFillEl) {
      coverageFillEl.style.width = Math.min(ratio, 150) + '%';
    }

    if (coverageStatusEl) {
      const status =
        ratio >= 105 ? 'Healthy' : ratio >= 100 ? 'Warning' : 'Deficit';
      coverageStatusEl.textContent = status;
    }

    if (excessEl) {
      const excess =
        data.offchain.total_reserves - data.onchain.net_circulation;
      excessEl.textContent = formatKRW(excess);
    }

    if (collateralTsEl) {
      collateralTsEl.textContent = new Date(
        data.coverage.timestamp
      ).toLocaleString('ko-KR');
    }

    // OffChain
    const totalReservesEl = this.container.querySelector('#totalReservesMain');
    const custodianListEl = this.container.querySelector('#custodianList');
    const offchainTsEl = this.container.querySelector('#offchainTimestamp');

    if (totalReservesEl) {
      totalReservesEl.textContent = formatKRW(data.offchain.total_reserves);
    }

    if (custodianListEl) {
      custodianListEl.innerHTML = (data.offchain.custodians || [])
        .map(
          (c) => `
          <li class="custodian-item">
            <span class="custodian-name">${c.name}</span>
            <span class="custodian-amount">${formatKRW(c.amount)}</span>
          </li>
        `
        )
        .join('');
    }

    if (offchainTsEl) {
      offchainTsEl.textContent = new Date(
        data.offchain.timestamp
      ).toLocaleString('ko-KR');
    }
  }

  // -----------------------------------
  // 동적 시각화 렌더링
  // (Chat.handleMetadata 에서 state.activeVisualizations에 넣은 것들)
  // -----------------------------------
  renderVisualizations(visualizations) {
    const container = this.container.querySelector('#dynamicVisualizations');
    if (!container) return;

    container.innerHTML = '';

    if (!visualizations || visualizations.length === 0) {
      // 동적 모드 아닐 때는 아무 것도 안 보여줘도 됨
      return;
    }

    visualizations.forEach((viz) => {
      const card = document.createElement('div');
      card.className = 'content-card dynamic-card animate-fade-in';

      const header = document.createElement('div');
      header.className = 'card-header';
      header.innerHTML = `
        <div class="card-title-section">
          <span class="card-icon">📈</span>
          <span class="card-title">${viz.title || 'Visualization'}</span>
        </div>
      `;
      card.appendChild(header);

      const body = document.createElement('div');
      body.style.flex = '1';

      switch (viz.type) {
        case 'bar_chart':
          this.renderBarChart(body, viz.data);
          break;
        case 'table':
          this.renderTable(body, viz.data);
          break;
        case 'status_card':
          this.renderStatusCard(body, viz.data);
          break;
        case 'gauge':
          this.renderGauge(body, viz.data);
          break;
        case 'risk_card':
          this.renderRiskCard(body, viz.data);
          break;
        default:
          body.innerHTML = `<div class="data-subtitle">알 수 없는 시각화 타입: ${viz.type}</div>`;
      }

      card.appendChild(body);
      container.appendChild(card);
    });
  }

  // -----------------------------------
  // 시각화 helper들
  // -----------------------------------
  renderBarChart(container, data) {
    // data: { labels: [], values: [], label: '...' }
    if (!data || !data.labels || !data.values) {
      container.innerHTML = '<div class="data-subtitle">표시할 데이터가 없습니다.</div>';
      return;
    }

    const max = Math.max(...data.values, 1);

    const wrapper = document.createElement('div');
    wrapper.className = 'chart-container';

    const rows = data.labels.map((label, i) => {
      const value = data.values[i];
      const width = (value / max) * 100;
      return `
        <div style="margin-bottom: 8px;">
          <div class="data-label" style="margin-bottom:4px;">${label}</div>
          <div style="
            height: 18px;
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border-color);
            position: relative;
          ">
            <div style="
              height: 100%;
              width: ${width}%;
              background: linear-gradient(90deg, var(--primary-orange), var(--light-orange));
              box-shadow: 0 0 8px rgba(255,107,53,0.5);
            "></div>
            <span style="
              position: absolute;
              right: 6px;
              top: 50%;
              transform: translateY(-50%);
              font-size: 11px;
            ">
              ${new Intl.NumberFormat('ko-KR').format(value)}
            </span>
          </div>
        </div>
      `;
    }).join('');

    wrapper.innerHTML = rows;
    container.appendChild(wrapper);
  }

  renderTable(container, data) {
    // data: { columns: [], rows: [ [..], .. ] }
    if (!data || !data.columns || !data.rows) {
      container.innerHTML = '<div class="data-subtitle">표시할 데이터가 없습니다.</div>';
      return;
    }

    const table = document.createElement('table');
    table.className = 'data-table';

    const thead = document.createElement('thead');
    thead.innerHTML = `
      <tr>
        ${data.columns.map(col => `<th>${col}</th>`).join('')}
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    tbody.innerHTML = data.rows.map(row => `
      <tr>
        ${row.map(cell => `<td>${cell}</td>`).join('')}
      </tr>
    `).join('');
    table.appendChild(tbody);

    container.appendChild(table);
  }

  renderStatusCard(container, data) {
    const status = data?.status || 'Unknown';
    const desc = data?.description || '';

    container.innerHTML = `
      <div class="data-row">
        <div class="data-label">정책 준수 현황</div>
        <div class="data-value">${status}</div>
        <div class="data-subtitle">${desc}</div>
      </div>
    `;
  }

  renderGauge(container, data) {
    const value = data?.value ?? 0;
    const clamped = Math.max(0, Math.min(200, value));

    container.innerHTML = `
      <div class="data-row">
        <div class="data-label">담보 커버리지</div>
        <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:12px;">
          <span class="card-value">${value}</span>
          <span style="font-size:24px;color:var(--text-secondary);font-weight:700;">%</span>
        </div>
        <div class="coverage-bar">
          <div class="coverage-fill" style="width:${clamped}%;"></div>
        </div>
        <div class="data-subtitle" style="margin-top:8px;">
          100% 이상 유지가 권장됩니다.
        </div>
      </div>
    `;
  }

  renderRiskCard(container, data) {
    const level = data?.level || 'LOW';
    const desc = data?.description || '';

    const colorMap = {
      HIGH: 'var(--danger)',
      MEDIUM: 'var(--warning)',
      LOW: 'var(--success)'
    };

    container.innerHTML = `
      <div class="data-row">
        <div class="data-label">리스크 수준</div>
        <div class="data-value" style="color:${colorMap[level] || 'var(--text-primary)'};">
          ${level}
        </div>
        <div class="data-subtitle">${desc}</div>
      </div>
    `;
  }
}

export default Dashboard;
