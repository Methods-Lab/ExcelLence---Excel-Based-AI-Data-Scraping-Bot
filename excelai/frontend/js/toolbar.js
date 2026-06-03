(function () {
  const ICONS = {
    'file-plus': '📁',
    file: '💾',
    'file-text': '📄',
    'file-pdf': '🧾',
    sparkles: '✨',
    type: '⌨️',
    image: '🖼️',
    link: '🔗',
    'edit-2': '✏️',
    'refresh-cw': '↻',
    'trash-2': '🗑️',
    code: '{}',
    'bar-chart-2': '📊',
    'log-out': '⎋',
    'message-square': '💬',
  };

  function groupButton(action, iconName, label, active = false, disabled = false) {
    return `
      <button class="toolbar-button ${active ? 'active' : ''}" data-action="${action}" ${disabled ? 'disabled' : ''} aria-label="${label}" title="${label}">
        <span class="state-dot" aria-hidden="true"></span>
        <span class="icon" aria-hidden="true">${ICONS[iconName] || '•'}</span>
        <span class="label">${label}</span>
      </button>`;
  }

  function renderToolbar(container, state) {
    container.innerHTML = `
      <div class="toolbar-brand">
        <div class="brand-mark">XL</div>
        <div class="brand-copy">
          <strong>ExcelLence</strong>
          <span>Premium data workspace</span>
        </div>
      </div>

      <div class="toolbar-ribbon">
        <div class="ribbon-tabs" aria-label="Ribbon sections">
          <button class="ribbon-tab active" type="button">Home</button>
          <button class="ribbon-tab" type="button">Insert</button>
          <button class="ribbon-tab" type="button">View</button>
          <button class="ribbon-tab" type="button">Export</button>
        </div>

        <div class="ribbon-groups">
          <div class="ribbon-group">
            <div class="ribbon-label">Session</div>
            <div class="toolbar-group" role="toolbar" aria-label="Session actions">
              ${groupButton('new-session', 'file-plus', 'New Session')}
              ${groupButton('export-xlsx', 'file', 'Export to Excel', false, !state.hasData)}
              ${groupButton('export-csv', 'file-text', 'Export as CSV', false, !state.hasData)}
              ${groupButton('export-pdf', 'file-pdf', 'Export as PDF', false, !state.hasData)}
            </div>
          </div>

          <div class="ribbon-group">
            <div class="ribbon-label">Report</div>
            <div class="toolbar-group" role="toolbar" aria-label="Report actions">
              ${groupButton('build-workbook', 'sparkles', 'Polished Workbook', false, !state.hasData)}
            </div>
          </div>

          <div class="ribbon-group">
            <div class="ribbon-label">Input</div>
            <div class="toolbar-group" role="toolbar" aria-label="Input mode">
              ${groupButton('mode-text', 'type', 'Text Input', state.mode === 'text')}
              ${groupButton('mode-image', 'image', 'Upload Image', state.mode === 'image')}
              ${groupButton('mode-url', 'link', 'From URL', state.mode === 'url')}
            </div>
          </div>

          <div class="ribbon-group">
            <div class="ribbon-label">Table</div>
            <div class="toolbar-group" role="toolbar" aria-label="Table actions">
              ${groupButton('edit-mode', 'edit-2', 'Edit Mode', state.editMode)}
              ${groupButton('reextract', 'refresh-cw', 'Re-Extract', false, !state.canReextract)}
              ${groupButton('clear-table', 'trash-2', 'Clear Table', false, !state.hasData)}
            </div>
          </div>

          <div class="ribbon-group">
            <div class="ribbon-label">View</div>
            <div class="toolbar-group" role="toolbar" aria-label="View toggles">
              ${groupButton('raw-json', 'code', 'Raw JSON', state.showRawJson, !state.hasData)}
              ${groupButton('column-stats', 'bar-chart-2', 'Column Stats', state.showStats, !state.hasData)}
            </div>
          </div>
        </div>
      </div>

      <div class="account-chip">
        <div class="account-avatar">${(state.user?.name || 'E').slice(0, 1).toUpperCase()}</div>
        <div class="account-copy">
          <strong>${state.user?.name || 'ExcelAI User'}</strong>
          <span>${state.user?.email || ''}</span>
        </div>
        ${groupButton('logout', 'log-out', 'Logout')}
      </div>`;
  }

  window.ExcelAI = window.ExcelAI || {};
  window.ExcelAI.Toolbar = { renderToolbar };
})();
