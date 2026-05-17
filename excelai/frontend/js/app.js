(function () {
  const token = window.ExcelAI.getToken();
  if (!token || !window.ExcelAI.isTokenValid(token)) {
    window.ExcelAI.clearToken();
    window.location.href = 'index.html';
    return;
  }

  const toolbar = document.getElementById('toolbar');
  const messageStream = document.getElementById('messageStream');
  const tableWrapper = document.getElementById('tableWrapper');
  const emptyState = document.getElementById('emptyState');
  const rawJsonPanel = document.getElementById('rawJsonPanel');
  const confirmationBar = document.getElementById('confirmationBar');
  const confirmationText = document.getElementById('confirmationText');
  const confirmationSubtext = document.getElementById('confirmationSubtext');
  const shapeBadge = document.getElementById('shapeBadge');
  const confidenceBadge = document.getElementById('confidenceBadge');
  const tableMeta = document.getElementById('tableMeta');
  const sessionStatus = document.getElementById('sessionStatus');
  const lastAction = document.getElementById('lastAction');
  const modelPulse = document.getElementById('modelPulse');
  const imageInput = document.getElementById('imageFile');
  const imagePreview = document.getElementById('imagePreview');
  const toolbarImageInput = document.getElementById('toolbarImageInput');
  const dropzone = document.getElementById('dropzone');

  const state = {
    user: null,
    mode: 'text',
    editMode: false,
    showRawJson: false,
    showStats: false,
    hasData: false,
    canReextract: false,
    currentData: null,
    sortState: null,
    page: 1,
    pageSize: 50,
    loading: false,
    lastExtraction: null,
    lastActionAt: new Date(),
  };

  function setStatus(text) {
    sessionStatus.textContent = text;
    state.lastActionAt = new Date();
    lastAction.textContent = `Last action: ${state.lastActionAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }

  function addMessage(kind, text, meta = []) {
    const message = document.createElement('div');
    message.className = `message ${kind}`;
    message.innerHTML = `<div>${text}</div>`;
    if (meta.length) {
      const metaWrap = document.createElement('div');
      metaWrap.className = 'message-meta';
      meta.forEach((item) => {
        const badge = document.createElement('span');
        badge.className = 'badge badge-soft';
        badge.textContent = item;
        metaWrap.appendChild(badge);
      });
      message.appendChild(metaWrap);
    }
    messageStream.appendChild(message);
    messageStream.scrollTop = messageStream.scrollHeight;
  }

  function addSystemMessage(text) {
    addMessage('system', text);
  }

  function isPreviewableFile(file) {
    return Boolean(file) && file.type.startsWith('image/');
  }

  function updateUploadPreview(file) {
    if (!file || !isPreviewableFile(file)) {
      imagePreview.removeAttribute('src');
      imagePreview.classList.add('hidden');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      imagePreview.src = String(reader.result);
      imagePreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
  }

  function addUserMessage(text) {
    addMessage('user', text);
  }

  function addAiMessage(text, confidence, sourceType) {
    const meta = [`Confidence: ${(confidence * 100).toFixed(0)}%`, `Source: ${sourceType}`, new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })];
    addMessage('ai', text, meta);
  }

  function collectCalculations() {
    const rows = [];
    document.querySelectorAll('#calcRows .calc-row').forEach((el) => {
      const name = el.querySelector('.calc-name').value.trim();
      const formula = el.querySelector('.calc-formula').value.trim();
      if (name && formula) rows.push({ name, formula });
    });
    return rows;
  }

  function showTopicSelector(detect) {
    return new Promise((resolve) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'message system';
      const list = document.createElement('div');
      list.style.display = 'grid';
      list.style.gap = '8px';
      list.style.maxHeight = '240px';
      list.style.overflow = 'auto';

      const selectedIds = new Set();
      detect.topics.forEach((topic) => {
        const title = document.createElement('div');
        title.style.fontWeight = '600';
        title.textContent = topic.name;
        list.appendChild(title);
        topic.sub_tables.forEach((sub) => {
          const row = document.createElement('label');
          row.style.display = 'flex';
          row.style.alignItems = 'center';
          row.style.gap = '8px';
          const cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.value = sub.id;
          cb.addEventListener('change', () => {
            if (cb.checked) selectedIds.add(sub.id); else selectedIds.delete(sub.id);
          });
          const txt = document.createElement('span');
          txt.textContent = `${sub.name} — ${sub.estimated_rows} rows`;
          row.appendChild(cb);
          row.appendChild(txt);
          list.appendChild(row);
        });
      });

      const actions = document.createElement('div');
      actions.style.display = 'flex';
      actions.style.gap = '8px';
      actions.style.marginTop = '8px';
      const btnExtract = document.createElement('button');
      btnExtract.className = 'primary-btn';
      btnExtract.textContent = 'Extract Selected';
      btnExtract.addEventListener('click', () => {
        wrapper.remove();
        resolve(Array.from(selectedIds));
      });
      const btnCancel = document.createElement('button');
      btnCancel.className = 'ghost-btn';
      btnCancel.textContent = 'Cancel';
      btnCancel.addEventListener('click', () => {
        wrapper.remove();
        resolve([]);
      });
      actions.appendChild(btnCancel);
      actions.appendChild(btnExtract);

      wrapper.appendChild(list);
      wrapper.appendChild(actions);
      messageStream.appendChild(wrapper);
      messageStream.scrollTop = messageStream.scrollHeight;
    });
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll('.mode-btn').forEach((button) => button.classList.toggle('active', button.dataset.mode === mode));
    document.querySelectorAll('.mode-form').forEach((form) => form.classList.toggle('hidden', form.dataset.formMode !== mode));
    refreshToolbar();
  }

  function refreshToolbar() {
    window.ExcelAI.Toolbar.renderToolbar(toolbar, {
      user: state.user,
      mode: state.mode,
      editMode: state.editMode,
      showRawJson: state.showRawJson,
      showStats: state.showStats,
      hasData: Boolean(state.currentData),
      canReextract: Boolean(state.lastExtraction),
    });
  }

  function renderTableView() {
    const data = state.currentData;
    if (!data) {
      emptyState.classList.remove('hidden');
      tableWrapper.classList.add('hidden');
      rawJsonPanel.classList.add('hidden');
      confirmationBar.classList.add('hidden');
      tableMeta.textContent = 'Your extracted table will appear here.';
      shapeBadge.textContent = '0 rows × 0 columns';
      confidenceBadge.textContent = 'Confidence: --';
      return;
    }

    emptyState.classList.add('hidden');
    tableWrapper.classList.remove('hidden');

    const result = window.ExcelAI.Table.renderTable(tableWrapper, data, {
      editMode: state.editMode,
      sortState: state.sortState,
      page: state.page,
      pageSize: state.pageSize,
      onSort: handleSort,
      onCellEdit: handleCellEdit,
    });

    state.hasData = true;
    shapeBadge.textContent = `${result.totalRows} rows × ${result.totalColumns} columns`;
    confidenceBadge.textContent = `Confidence: ${(data.confidence * 100).toFixed(0)}%`;
    tableMeta.textContent = data.table_title || `Source: ${data.source_type}`;
    confirmationBar.classList.remove('hidden');
    confirmationText.textContent = `AI has extracted ${result.totalRows} rows × ${result.totalColumns} columns from ${data.source_type}.`;
    confirmationSubtext.textContent = 'Review the preview before exporting.';

    if (state.showRawJson) {
      rawJsonPanel.classList.remove('hidden');
      window.ExcelAI.Table.renderRawJson(rawJsonPanel, data);
    } else if (state.showStats) {
      rawJsonPanel.classList.remove('hidden');
      window.ExcelAI.Table.renderStatsPanel(rawJsonPanel, data);
    } else {
      rawJsonPanel.classList.add('hidden');
    }
  }

  function setLoading(isLoading, label = 'Extracting...') {
    state.loading = isLoading;
    modelPulse.style.opacity = isLoading ? '1' : '0.6';
    if (isLoading) {
      setStatus(label);
      window.ExcelAI.Table.renderSkeleton(tableWrapper);
      emptyState.classList.add('hidden');
      tableWrapper.classList.remove('hidden');
      rawJsonPanel.classList.add('hidden');
      confirmationBar.classList.add('hidden');
      refreshToolbar();
      if (window.innerWidth < 1180) {
        window.ExcelAI.showToast('Best experienced on desktop for the full workspace layout.', 'info');
      }
    } else {
      setStatus('Ready');
      refreshToolbar();
    }
  }

  function updateCurrentData(nextData) {
    state.currentData = {
      columns: nextData.columns,
      rows: nextData.rows,
      confidence: nextData.confidence,
      source_type: nextData.source_type,
      warnings: nextData.warnings || [],
      table_title: nextData.table_title || null,
      ocr_raw_text: nextData.ocr_raw_text || null,
    };
    state.sortState = null;
    state.page = 1;
    state.hasData = true;
    renderTableView();
    refreshToolbar();
  }

  function handleSort(columnIndex) {
    if (!state.currentData) return;
    const sameColumn = state.sortState && state.sortState.index === columnIndex;
    state.sortState = {
      index: columnIndex,
      direction: sameColumn && state.sortState.direction === 'asc' ? 'desc' : 'asc',
    };
    renderTableView();
  }

  function handleCellEdit(rowIndex, columnIndex, value) {
    if (!state.currentData) return;
    if (!state.currentData.rows[rowIndex]) return;
    state.currentData.rows[rowIndex][columnIndex] = value;
  }

  function clearCurrentTable(keepMessages = false) {
    state.currentData = null;
    state.sortState = null;
    state.page = 1;
    state.hasData = false;
    state.canReextract = Boolean(state.lastExtraction);
    if (!keepMessages) {
      messageStream.innerHTML = '';
      addSystemMessage('Session reset. Enter new data to extract a fresh table.');
    }
    renderTableView();
    refreshToolbar();
    setStatus('Ready');
  }

  async function executeExtraction(kind, payload) {
    setLoading(true, 'Extracting…');
    try {
      let response;
      if (kind === 'text') {
        addUserMessage(payload.prompt);
        const calculations = collectCalculations();
        // Include calculated columns with text extraction so server can apply BODMAS rules
        response = await window.ExcelAI.request('/api/extract/text', {
          method: 'POST',
          body: JSON.stringify({ prompt: payload.prompt, calculated_columns: calculations }),
        });
      } else if (kind === 'image') {
        addUserMessage(`Image uploaded: ${payload.file.name}`);
        // First perform OCR-only to detect topics
        const ocrForm = new FormData();
        ocrForm.append('file', payload.file);
        const ocrResp = await window.ExcelAI.request('/api/extract/ocr', { method: 'POST', body: ocrForm });
        // Detect topics from OCR text
        const detect = await window.ExcelAI.request('/api/extract/detect-topics', {
          method: 'POST',
          body: JSON.stringify({ content_type: 'image', content: ocrResp.text }),
        });
        if (detect.topics && detect.topics.length) {
          const selected = await showTopicSelector(detect);
          if (!selected || selected.length === 0) {
            window.ExcelAI.showToast('Please select at least one table to extract.', 'warning');
            setLoading(false);
            return;
          }
          const calculations = collectCalculations();
          response = await window.ExcelAI.request('/api/extract/selected-topics', {
            method: 'POST',
            body: JSON.stringify({ content: ocrResp.text, selected_ids: selected, calculated_columns: calculations }),
          });
        } else {
          // fallback to direct image extraction
          const formData = new FormData();
          formData.append('file', payload.file);
          formData.append('instruction', payload.instruction || '');
          response = await window.ExcelAI.request('/api/extract/image', { method: 'POST', body: formData });
        }
      } else if (kind === 'url') {
        addUserMessage(payload.url);
        // First, detect topics and receive scraped content
        const detect = await window.ExcelAI.request('/api/extract/detect-topics', {
          method: 'POST',
          body: JSON.stringify({ content_type: 'url', content: payload.url }),
        });
        // If topics found, present selector and let user choose
        if (detect.topics && detect.topics.length) {
          const selected = await showTopicSelector(detect);
          if (!selected || selected.length === 0) {
            window.ExcelAI.showToast('Please select at least one table to extract.', 'warning');
            setLoading(false);
            return;
          }
          // send selected topics request with scraped content and calculations
          const calculations = collectCalculations();
          response = await window.ExcelAI.request('/api/extract/selected-topics', {
            method: 'POST',
            body: JSON.stringify({ content: detect.scraped_content || payload.url, selected_ids: selected, calculated_columns: calculations }),
          });
        } else {
          // fall back to direct URL extraction
          response = await window.ExcelAI.request('/api/extract/url', {
            method: 'POST',
            body: JSON.stringify({ url: payload.url, clarification: payload.clarification || '' }),
          });
        }
      } else if (kind === 'url') {
        // legacy path handled above
        response = null;
      }

      state.lastExtraction = { kind, payload };
      updateCurrentData(response);
      addAiMessage(`Extraction complete. ${response.warnings?.length ? 'Warnings need review.' : 'No warnings were returned.'}`, response.confidence, response.source_type);
      if (response.warnings && response.warnings.length) {
        response.warnings.forEach((warning) => addSystemMessage(warning));
      }
      setStatus('Ready');
      window.ExcelAI.showToast('Extraction completed successfully.', 'success');
    } catch (error) {
      addSystemMessage(`Extraction failed: ${error.message}`);
      window.ExcelAI.showToast(error.message || 'Extraction failed', 'error');
      setStatus('Extraction failed');
    } finally {
      setLoading(false);
      renderTableView();
      refreshToolbar();
    }
  }

  async function exportExcel() {
    if (!state.currentData) {
      window.ExcelAI.showToast('No table data to export.', 'warning');
      return;
    }
    try {
      await window.ExcelAI.download('/api/export/excel', {
        columns: state.currentData.columns,
        rows: state.currentData.rows,
        filename: 'ExcelLence_Export.xlsx',
      }, 'ExcelLence_Export.xlsx');
      setStatus('Export complete');
      window.ExcelAI.showToast('Excel file downloaded.', 'success');
    } catch (error) {
      window.ExcelAI.showToast(error.message || 'Excel export failed', 'error');
    }
  }

  async function exportCsv() {
    if (!state.currentData) {
      window.ExcelAI.showToast('No table data to export.', 'warning');
      return;
    }
    try {
      await window.ExcelAI.download('/api/export/csv', {
        columns: state.currentData.columns,
        rows: state.currentData.rows,
        filename: 'ExcelLence_Export.csv',
      }, 'ExcelLence_Export.csv');
      setStatus('Export complete');
      window.ExcelAI.showToast('CSV file downloaded.', 'success');
    } catch (error) {
      window.ExcelAI.showToast(error.message || 'CSV export failed', 'error');
    }
  }

  async function exportPdf() {
    if (!state.currentData) {
      window.ExcelAI.showToast('No table data to export.', 'warning');
      return;
    }
    try {
      await window.ExcelAI.download('/api/export/pdf', {
        columns: state.currentData.columns,
        rows: state.currentData.rows,
        filename: 'ExcelLence_Export.pdf',
      }, 'ExcelLence_Export.pdf');
      setStatus('PDF export complete');
      window.ExcelAI.showToast('PDF downloaded.', 'success');
    } catch (error) {
      window.ExcelAI.showToast(error.message || 'PDF export failed', 'error');
    }
  }

  async function loadUser() {
    try {
      state.user = await window.ExcelAI.request('/api/auth/me', { method: 'GET' });
    } catch (error) {
      window.ExcelAI.clearToken();
      window.location.href = 'index.html';
      return;
    }
    refreshToolbar();
  }

  function showRawJson() {
    state.showRawJson = !state.showRawJson;
    state.showStats = false;
    renderTableView();
    refreshToolbar();
  }

  function showColumnStats() {
    state.showStats = !state.showStats;
    state.showRawJson = false;
    renderTableView();
    refreshToolbar();
  }

  function openImagePicker() {
    toolbarImageInput.click();
  }

  function handleToolbarAction(action) {
    switch (action) {
      case 'new-session':
        state.lastExtraction = null;
        setMode('text');
        clearCurrentTable(false);
        document.getElementById('textPrompt').value = '';
        document.getElementById('imageInstruction').value = '';
        document.getElementById('urlInput').value = '';
        document.getElementById('urlClarification').value = '';
        imageInput.value = '';
        imagePreview.classList.add('hidden');
        window.ExcelAI.showToast('New session started.', 'info');
        break;
      case 'export-xlsx':
        exportExcel().catch(() => {});
        break;
      case 'export-csv':
        exportCsv().catch(() => {});
        break;
      case 'export-pdf':
        exportPdf().catch(() => {});
        break;
      case 'mode-text':
        setMode('text');
        break;
      case 'mode-image':
        setMode('image');
        openImagePicker();
        break;
      case 'mode-url':
        setMode('url');
        break;
      case 'edit-mode':
        state.editMode = !state.editMode;
        renderTableView();
        refreshToolbar();
        window.ExcelAI.showToast(state.editMode ? 'Edit mode enabled.' : 'Edit mode disabled.', 'info');
        break;
      case 'reextract':
        if (state.lastExtraction) {
          executeExtraction(state.lastExtraction.kind, state.lastExtraction.payload).catch(() => {});
        }
        break;
      case 'clear-table':
        state.currentData = null;
        state.sortState = null;
        state.page = 1;
        renderTableView();
        refreshToolbar();
        window.ExcelAI.showToast('Table cleared.', 'info');
        break;
      case 'raw-json':
        showRawJson();
        break;
      case 'column-stats':
        showColumnStats();
        break;
      case 'logout':
        window.ExcelAI.clearToken();
        window.location.href = 'index.html';
        break;
      default:
        break;
    }
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    handleToolbarAction(button.dataset.action);
  });

  document.querySelectorAll('.mode-btn').forEach((button) => {
    button.addEventListener('click', () => setMode(button.dataset.mode));
  });

  document.getElementById('textForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const prompt = document.getElementById('textPrompt').value.trim();
    if (!prompt) {
      window.ExcelAI.showToast('Enter a prompt before extracting.', 'warning');
      return;
    }
    await executeExtraction('text', { prompt });
  });

  document.getElementById('imageForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const file = imageInput.files[0];
    if (!file) {
      window.ExcelAI.showToast('Choose an image before extracting.', 'warning');
      return;
    }
    const instruction = document.getElementById('imageInstruction').value.trim();
    await executeExtraction('image', { file, instruction });
  });

  document.getElementById('urlForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
      window.ExcelAI.showToast('Enter a valid URL before extracting.', 'warning');
      return;
    }
    const clarification = document.getElementById('urlClarification').value.trim();
    await executeExtraction('url', { url, clarification });
  });

  imageInput.addEventListener('change', () => {
    const file = imageInput.files[0];
    updateUploadPreview(file);
  });

  toolbarImageInput.addEventListener('change', () => {
    const file = toolbarImageInput.files[0];
    if (!file) return;
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    imageInput.files = dataTransfer.files;
    updateUploadPreview(file);
    setMode('image');
  });

  dropzone.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropzone.style.borderColor = 'rgba(0, 255, 136, 0.6)';
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.style.borderColor = 'rgba(0, 255, 136, 0.24)';
  });

  dropzone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropzone.style.borderColor = 'rgba(0, 255, 136, 0.24)';
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    imageInput.files = dataTransfer.files;
    updateUploadPreview(file);
    setMode('image');
  });

  document.getElementById('editBeforeExport').addEventListener('click', () => {
    state.editMode = true;
    renderTableView();
    refreshToolbar();
  });

  document.getElementById('confirmExport').addEventListener('click', () => {
    exportExcel().catch(() => {});
  });

  document.getElementById('reextractButton').addEventListener('click', () => {
    if (state.lastExtraction) {
      executeExtraction(state.lastExtraction.kind, state.lastExtraction.payload).catch(() => {});
    }
  });

  // Calculation builder wiring
  const addCalcBtn = document.getElementById('addCalcBtn');
  const calcRows = document.getElementById('calcRows');
  if (addCalcBtn && calcRows) {
    addCalcBtn.addEventListener('click', () => {
      const nameInput = document.getElementById('newCalcName');
      const formulaInput = document.getElementById('newCalcFormula');
      const name = nameInput.value.trim();
      const formula = formulaInput.value.trim();
      if (!name || !formula) {
        window.ExcelAI.showToast('Enter name and formula for the calculated column.', 'warning');
        return;
      }
      const row = document.createElement('div');
      row.className = 'calc-row';
      row.style.display = 'flex';
      row.style.gap = '8px';
      row.innerHTML = `
        <input class="calc-name" value="${name}" style="flex:1;padding:8px;border:1px solid #E1E4E8;border-radius:6px;" />
        <input class="calc-formula" value="${formula}" style="flex:2;padding:8px;border:1px solid #E1E4E8;border-radius:6px;" />
        <button type="button" class="secondary-btn remove-calc">Remove</button>
      `;
      calcRows.appendChild(row);
      nameInput.value = '';
      formulaInput.value = '';
      row.querySelector('.remove-calc').addEventListener('click', () => row.remove());
    });
  }

  window.addEventListener('resize', () => {
    if (window.innerWidth < 1180) {
      document.body.style.overflow = 'auto';
    }
  });

  // Chat panel toggle: click the left vertical tab header to expand/collapse chat overlay
  (function setupChatToggle() {
    const chatPanel = document.querySelector('.chat-panel');
    const workspaceEl = document.querySelector('.workspace');
    if (!chatPanel) return;
    const header = chatPanel.querySelector('.panel-header');
    if (!header) return;
    const tabBtn = header.querySelector('.chat-tab') || header;
    tabBtn.style.cursor = 'pointer';
    tabBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const isExpanded = chatPanel.classList.toggle('expanded');
      if (workspaceEl) {
        workspaceEl.classList.toggle('chat-open', isExpanded);
      }
    });

    // Collapse when clicking outside — collapse both expanded and workspace state
    document.addEventListener('click', (ev) => {
      if (!chatPanel.classList.contains('expanded')) return;
      if (!chatPanel.contains(ev.target)) {
        chatPanel.classList.remove('expanded');
        if (workspaceEl) workspaceEl.classList.remove('chat-open');
      }
    });
  })();

  setStatus('Ready');
  addSystemMessage('ExcelLence is ready. Choose a data source on the left to begin extraction.');
  loadUser();
  refreshToolbar();
  renderTableView();
  setMode('text');
})();
