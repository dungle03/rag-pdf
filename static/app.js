document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const dom = {
    themeToggle: document.getElementById('theme-toggle'),
    fileInput: document.getElementById('file-input'),
    fileUploader: document.getElementById('file-uploader'),
    fileList: document.getElementById('file-list'),
    ingestButton: document.getElementById('btn-ingest'),
    ocrSwitch: document.getElementById('ocr-switch'),
    queryInput: document.getElementById('query-input'),
    askButton: document.getElementById('btn-ask'),
    chatContainer: document.getElementById('chat-container'),
    welcomeScreen: document.getElementById('welcome-screen'),
    docTitle: document.getElementById('doc-title'),
    knowledgeContent: document.getElementById('knowledge-content'),
    knowledgePlaceholder: document.getElementById('knowledge-placeholder'),
    citationsList: document.getElementById('citations-list'),
    statusIndicator: document.getElementById('status-indicator'),
    statusText: document.getElementById('status-text'),
    toastElement: document.getElementById('notification-toast'),
  };

  // --- State ---
  let state = {
    files: [], // { file: File, id: string, status: 'pending'|'uploading'|'uploaded'|'error' }
    sessionId: null,
    isIngesting: false,
    isAsking: false,
  };

  const bsToast = new bootstrap.Toast(dom.toastElement);

  // --- Utility Functions ---
  const showToast = (message, type = 'info') => {
    dom.toastElement.querySelector('.toast-body').textContent = message;
    dom.toastElement.className = `toast bg-${type === 'error' ? 'danger' : 'success'}`;
    bsToast.show();
  };

  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  const setStatus = (text, type = 'ready') => {
    dom.statusText.textContent = text;
    dom.statusIndicator.className = `status-indicator-${type}`;
  };

  // --- Theme Management ---
  const applyTheme = (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    const icon = dom.themeToggle.querySelector('i');
    icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
  };

  dom.themeToggle.addEventListener('click', () => {
    const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
  });

  // --- File Handling ---
  const renderFileList = () => {
    dom.fileList.innerHTML = '';
    if (state.files.length === 0) {
      dom.ingestButton.disabled = true;
      return;
    }

    state.files.forEach(fileWrapper => {
      const fileItem = document.createElement('div');
      fileItem.className = 'file-item';
      fileItem.dataset.id = fileWrapper.id;

      let statusIcon = '';
      switch (fileWrapper.status) {
        case 'uploading':
          statusIcon = `<div class="spinner-border spinner-border-sm text-primary" role="status"></div>`;
          break;
        case 'uploaded':
          statusIcon = `<i class="bi bi-check-circle-fill text-success"></i>`;
          break;
        case 'error':
          statusIcon = `<i class="bi bi-x-circle-fill text-danger"></i>`;
          break;
        default:
          statusIcon = `<i class="bi bi-file-earmark-arrow-up"></i>`;
      }

      fileItem.innerHTML = `
        <div class="file-info">
          <div class="file-icon"><i class="bi bi-file-earmark-pdf-fill"></i></div>
          <div class="file-details">
            <div class="file-name" title="${fileWrapper.file.name}">${fileWrapper.file.name}</div>
            <div class="file-status">${formatBytes(fileWrapper.file.size)}</div>
          </div>
        </div>
        <div class="file-actions">
          ${statusIcon}
          <button class="btn btn-icon btn-delete" data-id="${fileWrapper.id}" title="Xoá">
            <i class="bi bi-trash3"></i>
          </button>
        </div>
      `;
      dom.fileList.appendChild(fileItem);
    });

    dom.ingestButton.disabled = state.files.every(f => f.status !== 'uploaded');
  };

  const handleFiles = (files) => {
    const newFiles = Array.from(files)
      .filter(file => (file.type && file.type.toLowerCase().includes('pdf')) || file.name.toLowerCase().endsWith('.pdf'))
      .map(file => ({ file, id: `file-${Date.now()}-${Math.random()}`, status: 'pending' }));

    state.files.push(...newFiles);
    renderFileList();
    uploadFiles();
  };

  const uploadFiles = async () => {
    const pendingFiles = state.files.filter(f => f.status === 'pending');
    if (pendingFiles.length === 0) return;

    const formData = new FormData();
    if (state.sessionId) {
      formData.append('session_id', state.sessionId);
    }
    pendingFiles.forEach(fw => {
      fw.status = 'uploading';
      formData.append('files', fw.file);
    });
    renderFileList();

    try {
      const response = await fetch('/upload', { method: 'POST', body: formData });
      const result = await response.json();

      if (!response.ok) throw new Error(result.error || 'Upload failed');

      state.sessionId = result.session_id;
      let successfulUploads = 0;
      result.files.forEach(uploadedFile => {
        const serverName = uploadedFile.orig_name || uploadedFile.name;
        const serverSize = uploadedFile.size;
        const fileWrapper = state.files.find(
          fw => fw.status === 'uploading' && (
            fw.file.name === serverName || (serverSize && fw.file.size === serverSize)
          )
        );
        if (fileWrapper) {
          fileWrapper.status = 'uploaded';
          fileWrapper.serverDocName = uploadedFile.name;
          successfulUploads++;
        }
      });

      if (successfulUploads > 0) {
        showToast(`Đã tải lên thành công ${successfulUploads} file.`, 'success');
      }

    } catch (error) {
      showToast(`Lỗi tải lên: ${error.message}`, 'error');
      pendingFiles.forEach(fw => fw.status = 'error');
    } finally {
      renderFileList();
    }
  };

  dom.fileUploader.addEventListener('click', (e) => {
    if (e.target.tagName !== 'LABEL') {
      dom.fileInput.click();
    }
  });
  dom.fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dom.fileUploader.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });
  dom.fileUploader.addEventListener('dragover', () => dom.fileUploader.classList.add('drag-over'));
  dom.fileUploader.addEventListener('dragleave', () => dom.fileUploader.classList.remove('drag-over'));
  dom.fileUploader.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files));

  dom.fileList.addEventListener('click', (e) => {
    const button = e.target.closest('button');
    if (button && button.dataset.id) {
      state.files = state.files.filter(fw => fw.id !== button.dataset.id);
      renderFileList();
    }
  });

  // --- Ingesting ---
  dom.ingestButton.addEventListener('click', async () => {
    if (state.isIngesting || !state.sessionId) return;

    state.isIngesting = true;
    dom.ingestButton.disabled = true;
    setStatus('Đang xử lý...', 'processing');

    try {
      const formData = new FormData();
      formData.append('session_id', state.sessionId);
      formData.append('ocr', dom.ocrSwitch.checked);

      const response = await fetch('/ingest', { method: 'POST', body: formData });
      const result = await response.json();

      if (!response.ok) throw new Error(result.error || 'Ingest failed');

      showToast(`Đã xử lý thành công ${result.total_chunks} chunks từ ${result.ingested.length} tài liệu.`, 'success');
      dom.askButton.disabled = false;
      dom.queryInput.disabled = false;
      dom.queryInput.placeholder = "Bây giờ, hãy hỏi tôi điều gì đó...";
      if (result.ingested.length > 0) {
        dom.docTitle.textContent = result.ingested.map(d => d.doc).join(', ');
      }

    } catch (error) {
      showToast(`Lỗi xử lý: ${error.message}`, 'error');
    } finally {
      state.isIngesting = false;
      dom.ingestButton.disabled = state.files.every(f => f.status !== 'uploaded');
      setStatus('Sẵn sàng');
    }
  });

  // --- Chat ---
  const addChatMessage = (type, content) => {
    if (dom.welcomeScreen) {
      dom.welcomeScreen.remove();
    }
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${type}`;
    if (type === 'ai' && !content) {
      bubble.innerHTML = `<div class="d-flex align-items-center"><div class="dot-flashing"></div></div>`;
    } else {
      bubble.innerHTML = content; // Use innerHTML to render markdown
    }
    dom.chatContainer.appendChild(bubble);
    dom.chatContainer.scrollTop = dom.chatContainer.scrollHeight;
    return bubble;
  };

  const handleAsk = async () => {
    const query = dom.queryInput.value.trim();
    if (!query || state.isAsking) return;

    state.isAsking = true;
    dom.askButton.disabled = true;
    dom.queryInput.value = '';
    setStatus('AI đang suy nghĩ...', 'processing');
    addChatMessage('user', query);
    const loadingBubble = addChatMessage('ai', '');

    try {
      const formData = new FormData();
      formData.append('query', query);
      formData.append('session_id', state.sessionId);

      const response = await fetch('/ask', { method: 'POST', body: formData });
      const result = await response.json();

      if (!response.ok) throw new Error(result.error || 'Ask failed');

      loadingBubble.innerHTML = result.answer;
      renderCitations(result.sources);

    } catch (error) {
      loadingBubble.remove();
      addChatMessage('ai', `Rất tiếc, đã có lỗi xảy ra: ${error.message}`);
      showToast(error.message, 'error');
    } finally {
      state.isAsking = false;
      dom.askButton.disabled = false;
      setStatus('Sẵn sàng');
    }
  };

  const renderCitations = (sources) => {
    if (!sources || sources.length === 0) {
      dom.knowledgePlaceholder.style.display = 'block';
      dom.knowledgeContent.style.display = 'none';
      return;
    }

    dom.knowledgePlaceholder.style.display = 'none';
    dom.knowledgeContent.style.display = 'block';
    dom.citationsList.innerHTML = '';

    sources.forEach(source => {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
            <div class="card-body">
                <h6 class="card-title">
                    <span class="citation-tag" title="Click để xem chi tiết">${source.filename}:${source.page}</span>
                </h6>
                <p class="card-text small">${source.content}</p>
                <div class="text-end small text-muted">Score: ${source.score.toFixed(3)}</div>
            </div>
        `;
      dom.citationsList.appendChild(card);
    });
  };

  dom.askButton.addEventListener('click', handleAsk);
  dom.queryInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  });

  // --- Initialization ---
  const init = () => {
    const preferredTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(preferredTheme);
    dom.queryInput.disabled = true;
    renderFileList();
    setStatus('Sẵn sàng');
  };

  init();
});
