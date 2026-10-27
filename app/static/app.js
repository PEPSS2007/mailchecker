/**
 * Email Deliverability Checker — Frontend Dashboard Application
 */

(function () {
  'use strict';

  // Application State
  const state = {
    results: [],
    activeFilter: 'all',
    searchQuery: '',
    smtpAvailable: false,
    activeMode: 'unknown',
  };

  // DOM Elements
  const elements = {
    // Banner
    systemBanner: document.getElementById('systemBanner'),
    bannerDot: document.getElementById('bannerDot'),
    bannerText: document.getElementById('bannerText'),
    bannerBadge: document.getElementById('bannerBadge'),
    refreshHealthBtn: document.getElementById('refreshHealthBtn'),

    // Input & Actions
    emailInput: document.getElementById('emailInput'),
    detectedCount: document.getElementById('detectedCount'),
    checkEmailsBtn: document.getElementById('checkEmailsBtn'),
    clearInputBtn: document.getElementById('clearInputBtn'),
    btnSpinner: document.getElementById('btnSpinner'),
    btnText: document.getElementById('btnText'),

    // Samples
    sampleValidBtn: document.getElementById('sampleValidBtn'),
    sampleMixedBtn: document.getElementById('sampleMixedBtn'),
    sampleInvalidBtn: document.getElementById('sampleInvalidBtn'),

    // Progress & Alerts
    progressBarContainer: document.getElementById('progressBarContainer'),
    progressStatusText: document.getElementById('progressStatusText'),
    progressPercent: document.getElementById('progressPercent'),
    progressFill: document.getElementById('progressFill'),
    errorAlert: document.getElementById('errorAlert'),
    errorMessage: document.getElementById('errorMessage'),
    closeErrorBtn: document.getElementById('closeErrorBtn'),

    // Results & Metrics
    resultsSection: document.getElementById('resultsSection'),
    metricTotal: document.getElementById('metricTotal'),
    metricDeliverable: document.getElementById('metricDeliverable'),
    metricBounce: document.getElementById('metricBounce'),
    metricUnknown: document.getElementById('metricUnknown'),

    // Table & Filters
    resultsTableBody: document.getElementById('resultsTableBody'),
    emptySearchState: document.getElementById('emptySearchState'),
    tableSearch: document.getElementById('tableSearch'),
    filterTabs: document.querySelectorAll('.filter-tab'),
    tabCountAll: document.getElementById('tabCountAll'),
    tabCountDeliverable: document.getElementById('tabCountDeliverable'),
    tabCountBounce: document.getElementById('tabCountBounce'),
    tabCountUnknown: document.getElementById('tabCountUnknown'),

    // Action buttons
    copyResultsBtn: document.getElementById('copyResultsBtn'),
    exportCsvBtn: document.getElementById('exportCsvBtn'),
    clearResultsBtn: document.getElementById('clearResultsBtn'),

    // Toast
    toast: document.getElementById('toast'),
  };

  // Sample data presets
  const samplePresets = {
    valid: [
      'support@github.com',
      'contact@stripe.com',
      'info@cloudflare.com',
      'admin@python.org',
    ].join('\n'),

    mixed: [
      'support@github.com',
      'fake-user-not-real-992384@gmail.com',
      'test@10minutemail.com',
      'hello@nonexistent-domain-xyz-404.org',
      'admin@wikipedia.org',
    ].join(',\n'),

    invalid: [
      'plainaddress',
      'missing-at-sign.com',
      '@missing-username.com',
      'user@.invalid-starting-dot.com',
      'user@domain..com',
      'valid.user@example.com',
    ].join(';\n'),
  };

  /* ==========================================================================
     Utility Functions
     ========================================================================== */

  function parseInputTokens(text) {
    if (!text || typeof text !== 'string') return [];
    const tokens = text.split(/[\r\n,;\t\s]+/);
    const seen = new Set();
    const result = [];

    for (const item of tokens) {
      const clean = item.trim().replace(/^<|>|"|'$/g, '');
      if (clean && !seen.has(clean.toLowerCase())) {
        seen.add(clean.toLowerCase());
        result.push(clean);
      }
    }
    return result;
  }

  function showToast(message, duration = 3000) {
    elements.toast.textContent = message;
    elements.toast.classList.add('show');
    setTimeout(() => {
      elements.toast.classList.remove('show');
    }, duration);
  }

  function showError(message) {
    elements.errorMessage.textContent = message;
    elements.errorAlert.style.display = 'flex';
  }

  function hideError() {
    elements.errorAlert.style.display = 'none';
    elements.errorMessage.textContent = '';
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /* ==========================================================================
     Health & System Capability Check
     ========================================================================== */

  async function checkSystemHealth() {
    elements.bannerText.textContent = 'Probing outbound SMTP port 25 capability...';
    try {
      const response = await fetch('/api/health');
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();

      state.smtpAvailable = Boolean(data.smtp_available);
      state.activeMode = data.mode;

      if (state.smtpAvailable) {
        elements.systemBanner.classList.remove('mode-degraded');
        elements.bannerText.textContent =
          'Full Checks Active: Outbound SMTP port 25 is operational. Performing live mailbox verification.';
        elements.bannerBadge.textContent = 'Full Checks';
      } else {
        elements.systemBanner.classList.add('mode-degraded');
        elements.bannerText.textContent =
          'DNS-Only Degraded Mode: Outbound port 25 is blocked on this host. Testing syntax & DNS MX with honest unknown mailbox statuses.';
        elements.bannerBadge.textContent = 'DNS-Only Checks';
      }
    } catch (err) {
      console.warn('Health check failed:', err);
      elements.systemBanner.classList.add('mode-degraded');
      elements.bannerText.textContent =
        'Health probe unavailable. Operating in standard mode.';
      elements.bannerBadge.textContent = 'Offline Probe';
    }
  }

  /* ==========================================================================
     Input Handling & Live Counter
     ========================================================================== */

  function updateInputStats() {
    const tokens = parseInputTokens(elements.emailInput.value);
    elements.detectedCount.textContent = tokens.length;
    if (tokens.length > 100) {
      elements.detectedCount.style.color = '#ef4444';
      elements.checkEmailsBtn.disabled = true;
    } else {
      elements.detectedCount.style.color = '';
      elements.checkEmailsBtn.disabled = false;
    }
  }

  function loadSample(key) {
    if (samplePresets[key]) {
      elements.emailInput.value = samplePresets[key];
      updateInputStats();
      hideError();
    }
  }

  /* ==========================================================================
     Verification Execution
     ========================================================================== */

  async function runVerification() {
    hideError();
    const rawText = elements.emailInput.value.trim();
    const tokens = parseInputTokens(rawText);

    if (tokens.length === 0) {
      showError('Please paste at least one email address to check.');
      return;
    }

    if (tokens.length > 100) {
      showError(`Maximum 100 email addresses allowed per check (detected ${tokens.length}).`);
      return;
    }

    // Enter Loading State
    setLoadingState(true);
    updateProgress(15, 'Parsing syntax & resolving DNS records...');

    try {
      // Simulate progressive progress updates while request is in-flight
      const progressTimer = setInterval(() => {
        const current = parseInt(elements.progressPercent.textContent, 10);
        if (current < 85) {
          updateProgress(current + 15, 'Probing destination mail servers safely...');
        }
      }, 450);

      const response = await fetch('/api/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ emails: tokens }),
      });

      clearInterval(progressTimer);

      if (!response.ok) {
        let errMessage = `Server error (${response.status})`;
        try {
          const errData = await response.json();
          if (errData.detail) errMessage = errData.detail;
        } catch (_) {}
        throw new Error(errMessage);
      }

      updateProgress(100, 'Classification complete!');
      const data = await response.json();

      setTimeout(() => {
        setLoadingState(false);
        renderResults(data);
      }, 300);

    } catch (err) {
      setLoadingState(false);
      showError(err.message || 'Failed to complete verification. Please check your network and try again.');
    }
  }

  function setLoadingState(isLoading) {
    elements.checkEmailsBtn.disabled = isLoading;
    elements.clearInputBtn.disabled = isLoading;
    elements.emailInput.disabled = isLoading;

    if (isLoading) {
      elements.btnSpinner.style.display = 'inline-block';
      elements.btnText.textContent = 'Verifying...';
      elements.progressBarContainer.style.display = 'block';
    } else {
      elements.btnSpinner.style.display = 'none';
      elements.btnText.textContent = 'Check Emails';
      elements.progressBarContainer.style.display = 'none';
      updateProgress(0, '');
    }
  }

  function updateProgress(percent, label) {
    elements.progressPercent.textContent = `${percent}%`;
    elements.progressFill.style.width = `${percent}%`;
    if (label) elements.progressStatusText.textContent = label;
  }

  /* ==========================================================================
     Results Rendering & Filtering
     ========================================================================== */

  function renderResults(data) {
    state.results = data.results || [];

    // Update Metric Cards
    elements.metricTotal.textContent = data.total || 0;
    elements.metricDeliverable.textContent = data.deliverable || 0;
    elements.metricBounce.textContent = data.bounce || 0;
    elements.metricUnknown.textContent = data.unknown || 0;

    // Update Filter Tab Badges
    elements.tabCountAll.textContent = data.total || 0;
    elements.tabCountDeliverable.textContent = data.deliverable || 0;
    elements.tabCountBounce.textContent = data.bounce || 0;
    elements.tabCountUnknown.textContent = data.unknown || 0;

    // Display Results Container
    elements.resultsSection.style.display = 'block';
    elements.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Render Table Rows
    renderTableRows();
    showToast(`Successfully verified ${data.total} email address${data.total === 1 ? '' : 'es'}.`);
  }

  function getFilteredResults() {
    return state.results.filter((item) => {
      // Filter by verdict tab
      if (state.activeFilter !== 'all' && item.verdict !== state.activeFilter) {
        return false;
      }
      // Filter by search query
      if (state.searchQuery) {
        const query = state.searchQuery.toLowerCase();
        const emailMatch = item.email.toLowerCase().includes(query);
        const reasonMatch = item.reason.toLowerCase().includes(query);
        const explanationMatch = (item.explanation || '').toLowerCase().includes(query);
        return emailMatch || reasonMatch || explanationMatch;
      }
      return true;
    });
  }

  function renderTableRows() {
    const filtered = getFilteredResults();
    elements.resultsTableBody.innerHTML = '';

    if (filtered.length === 0) {
      elements.emptySearchState.style.display = 'block';
      return;
    }
    elements.emptySearchState.style.display = 'none';

    filtered.forEach((item) => {
      const tr = document.createElement('tr');

      // Flags HTML
      let flagsHtml = '—';
      if (item.flags && item.flags.length > 0) {
        flagsHtml = `
          <div class="flags-container">
            ${item.flags
              .map((flag) => {
                let flagClass = '';
                if (flag === 'disposable') flagClass = 'flag-disposable';
                else if (flag === 'role_account') flagClass = 'flag-role';
                else if (flag === 'catch_all') flagClass = 'flag-catch_all';
                return `<span class="flag-chip ${flagClass}" title="${escapeHtml(flag)}">${escapeHtml(flag)}</span>`;
              })
              .join('')}
          </div>
        `;
      }

      tr.innerHTML = `
        <td class="email-cell">${escapeHtml(item.email)}</td>
        <td>
          <span class="verdict-badge verdict-${escapeHtml(item.verdict)}">
            <span class="verdict-badge-dot"></span>
            ${escapeHtml(item.verdict)}
          </span>
        </td>
        <td><span class="reason-tag">${escapeHtml(item.reason)}</span></td>
        <td class="explanation-text">${escapeHtml(item.explanation)}</td>
        <td>${flagsHtml}</td>
      `;

      elements.resultsTableBody.appendChild(tr);
    });
  }

  /* ==========================================================================
     Export & Copy Actions
     ========================================================================== */

  function copyResultsToClipboard() {
    if (state.results.length === 0) {
      showToast('No results to copy.');
      return;
    }

    const rows = [
      ['Email', 'Verdict', 'Reason', 'Explanation', 'Flags'].join('\t'),
    ];

    state.results.forEach((r) => {
      rows.push(
        [
          r.email,
          r.verdict,
          r.reason,
          `"${(r.explanation || '').replace(/"/g, '""')}"`,
          (r.flags || []).join(';'),
        ].join('\t')
      );
    });

    navigator.clipboard
      .writeText(rows.join('\n'))
      .then(() => showToast('Results copied to clipboard!'))
      .catch(() => showToast('Failed to copy results.'));
  }

  function exportResultsCsv() {
    if (state.results.length === 0) {
      showToast('No results to export.');
      return;
    }

    const csvRows = ['Email,Verdict,Reason,Explanation,Flags'];
    state.results.forEach((r) => {
      const email = `"${r.email.replace(/"/g, '""')}"`;
      const verdict = `"${r.verdict.replace(/"/g, '""')}"`;
      const reason = `"${r.reason.replace(/"/g, '""')}"`;
      const explanation = `"${(r.explanation || '').replace(/"/g, '""')}"`;
      const flags = `"${(r.flags || []).join(';').replace(/"/g, '""')}"`;
      csvRows.push([email, verdict, reason, explanation, flags].join(','));
    });

    const blob = new Blob([csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `email_deliverability_results_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast('CSV downloaded successfully.');
  }

  function clearResults() {
    state.results = [];
    elements.resultsSection.style.display = 'none';
    elements.resultsTableBody.innerHTML = '';
    elements.tableSearch.value = '';
    state.searchQuery = '';
    showToast('Results cleared.');
  }

  function clearInput() {
    elements.emailInput.value = '';
    updateInputStats();
    hideError();
  }

  /* ==========================================================================
     Event Listeners Initializer
     ========================================================================== */

  function initEventListeners() {
    // Input events
    elements.emailInput.addEventListener('input', updateInputStats);
    elements.clearInputBtn.addEventListener('click', clearInput);
    elements.checkEmailsBtn.addEventListener('click', runVerification);
    elements.closeErrorBtn.addEventListener('click', hideError);

    // Refresh Health
    elements.refreshHealthBtn.addEventListener('click', () => {
      checkSystemHealth();
      showToast('Refreshing SMTP port 25 capability...');
    });

    // Sample buttons
    elements.sampleValidBtn.addEventListener('click', () => loadSample('valid'));
    elements.sampleMixedBtn.addEventListener('click', () => loadSample('mixed'));
    elements.sampleInvalidBtn.addEventListener('click', () => loadSample('invalid'));

    // Filter tabs
    elements.filterTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        elements.filterTabs.forEach((t) => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        state.activeFilter = tab.dataset.filter;
        renderTableRows();
      });
    });

    // Search input
    elements.tableSearch.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.trim();
      renderTableRows();
    });

    // Export & Action Buttons
    elements.copyResultsBtn.addEventListener('click', copyResultsToClipboard);
    elements.exportCsvBtn.addEventListener('click', exportResultsCsv);
    elements.clearResultsBtn.addEventListener('click', clearResults);
  }

  // Initial Boot
  document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    checkSystemHealth();
    updateInputStats();
  });
})();
