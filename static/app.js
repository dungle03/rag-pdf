console.log('RAG PDF JavaScript loaded!');

document.addEventListener('DOMContentLoaded', () => {
  // --- DOM Elements ---
  const dom = {
    themeToggle: document.getElementById('theme-toggle'),
    newSessionBtn: document.getElementById('btn-new-session'),
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

  // --- Session Management ---
  const saveSessionToStorage = (sessionId) => {
    if (sessionId) {
      localStorage.setItem('rag_pdf_session_id', sessionId);
      localStorage.setItem('rag_pdf_session_timestamp', Date.now().toString());
    }
  };

  const getSessionFromStorage = () => {
    const sessionId = localStorage.getItem('rag_pdf_session_id');
    const timestamp = localStorage.getItem('rag_pdf_session_timestamp');

    // Expire session after 24 hours
    if (sessionId && timestamp) {
      const age = Date.now() - parseInt(timestamp);
      const maxAge = 24 * 60 * 60 * 1000; // 24 hours

      if (age < maxAge) {
        return sessionId;
      } else {
        // Clear expired session
        localStorage.removeItem('rag_pdf_session_id');
        localStorage.removeItem('rag_pdf_session_timestamp');
      }
    }
    return null;
  };

  const clearSessionFromStorage = () => {
    localStorage.removeItem('rag_pdf_session_id');
    localStorage.removeItem('rag_pdf_session_timestamp');
  };

  // --- Restore Session ---
  const restoreSession = async () => {
    const savedSessionId = getSessionFromStorage();
    if (!savedSessionId) return false;

    try {
      setStatus('Đang khôi phục phiên làm việc...', 'processing');

      const response = await fetch(`/session/${savedSessionId}`);
      const result = await response.json();

      if (response.ok && result.session_found) {
        state.sessionId = savedSessionId;

        // Restore files
        state.files = result.files.map(file => ({
          file: null, // Không có File object, chỉ có metadata
          id: `file-${Date.now()}-${Math.random()}`,
          status: file.status,
          serverDocName: file.name,
          size: file.size,
          pages: file.pages,
          chunks: file.chunks,
          name: file.orig_name || file.name
        }));

        renderFileList();

        // Update UI based on session state
        if (result.can_ask) {
          dom.askButton.disabled = false;
          dom.queryInput.disabled = false;
          dom.queryInput.placeholder = "Bây giờ, hãy hỏi tôi điều gì đó...";

          // Update document title
          const docNames = result.files.map(f => f.name).join(', ');
          if (docNames) {
            dom.docTitle.textContent = docNames;
          }

          // Keep welcome screen visible - removed auto-hide logic
        }

        showToast(`Đã khôi phục phiên làm việc với ${result.files.length} tài liệu.`, 'success');
        setStatus('Đã khôi phục phiên làm việc', 'ready');
        return true;

      } else {
        // Session not found or invalid
        clearSessionFromStorage();
        setStatus('Sẵn sàng', 'ready');
        return false;
      }

    } catch (error) {
      console.error('Error restoring session:', error);
      clearSessionFromStorage();
      setStatus('Sẵn sàng', 'ready');
      return false;
    }
  };

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

  // --- New Session ---
  const startNewSession = () => {
    if (confirm('Bạn có chắc muốn bắt đầu phiên làm việc mới? Điều này sẽ xóa tất cả tài liệu và cuộc hội thoại hiện tại.')) {
      // Clear session storage
      clearSessionFromStorage();

      // Reset state
      state.files = [];
      state.sessionId = null;
      state.isIngesting = false;
      state.isAsking = false;

      // Reset UI
      renderFileList();
      dom.askButton.disabled = true;
      dom.queryInput.disabled = true;
      dom.queryInput.placeholder = "Hỏi điều gì đó về tài liệu của bạn...";
      dom.docTitle.textContent = '';
      dom.ingestButton.innerHTML = '<i class="bi bi-gear"></i> Xử lý & Vector hóa';
      dom.ingestButton.disabled = true;

      // Clear chat
      dom.chatContainer.innerHTML = `
        <div id="welcome-screen" class="welcome-screen">
          <div class="welcome-icon">🤖</div>
          <h3>Trợ lý tài liệu RAG xin chào!</h3>
          <p>Hãy bắt đầu bằng cách tải lên tài liệu PDF của bạn ở thanh bên trái.</p>
          <div class="onboarding-steps">
            <div class="step"><span>1</span> Tải lên PDF</div>
            <div class="step"><span>2</span> Đặt câu hỏi</div>
            <div class="step"><span>3</span> Nhận câu trả lời & trích dẫn</div>
          </div>
        </div>
      `;
      dom.welcomeScreen = document.getElementById('welcome-screen');

      // Clear knowledge sidebar
      dom.knowledgePlaceholder.style.display = 'block';
      dom.knowledgeContent.style.display = 'none';

      setStatus('Sẵn sàng');
      showToast('Đã bắt đầu phiên làm việc mới.', 'success');
    }
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

  dom.newSessionBtn.addEventListener('click', startNewSession);

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
      let fileName = fileWrapper.name || (fileWrapper.file && fileWrapper.file.name) || 'Unknown file';
      let fileSize = fileWrapper.size || (fileWrapper.file && fileWrapper.file.size) || 0;

      switch (fileWrapper.status) {
        case 'uploading':
          statusIcon = `<div class="spinner-border spinner-border-sm text-primary" role="status"></div>`;
          break;
        case 'uploaded':
          statusIcon = `<i class="bi bi-check-circle-fill text-success"></i>`;
          break;
        case 'ingested':
          statusIcon = `<i class="bi bi-check-circle-fill text-success"></i>`;
          break;
        case 'error':
          statusIcon = `<i class="bi bi-x-circle-fill text-danger"></i>`;
          break;
        default:
          statusIcon = `<i class="bi bi-file-earmark-arrow-up"></i>`;
      }

      // Show additional info for ingested files
      let additionalInfo = '';
      if (fileWrapper.status === 'ingested' && fileWrapper.pages && fileWrapper.chunks) {
        additionalInfo = ` • ${fileWrapper.pages} trang • ${fileWrapper.chunks} chunks`;
      }

      fileItem.innerHTML = `
        <div class="file-info">
          <div class="file-icon"><i class="bi bi-file-earmark-pdf-fill"></i></div>
          <div class="file-details">
            <div class="file-name" title="${fileName}">${fileName}</div>
            <div class="file-status">${formatBytes(fileSize)}${additionalInfo}</div>
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

    // Enable ingest button only if there are uploaded files that haven't been ingested
    const hasUploadedFiles = state.files.some(f => f.status === 'uploaded');
    const hasIngestedFiles = state.files.some(f => f.status === 'ingested');

    dom.ingestButton.disabled = !hasUploadedFiles;

    // If all files are ingested, change button text
    if (hasIngestedFiles && !hasUploadedFiles) {
      dom.ingestButton.textContent = '✓ Đã xử lý';
      dom.ingestButton.disabled = true;
    } else {
      dom.ingestButton.innerHTML = '<i class="bi bi-gear"></i> Xử lý & Vector hóa';
    }
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
      saveSessionToStorage(state.sessionId); // Save session to localStorage

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
        // Removed duplicate saveSessionToStorage call
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

      // Update file status to 'ingested'
      result.ingested.forEach(ingested => {
        const fileWrapper = state.files.find(fw => fw.serverDocName === ingested.doc);
        if (fileWrapper) {
          fileWrapper.status = 'ingested';
          fileWrapper.pages = ingested.pages;
          fileWrapper.chunks = ingested.chunks;
        }
      });

      renderFileList(); // Re-render to show updated status

      dom.askButton.disabled = false;
      dom.queryInput.disabled = false;
      dom.queryInput.placeholder = "Bây giờ, hãy hỏi tôi điều gì đó...";
      if (result.ingested.length > 0) {
        dom.docTitle.textContent = result.ingested.map(d => d.doc).join(', ');
      }

      saveSessionToStorage(state.sessionId); // Update session timestamp

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
  const init = async () => {
    const preferredTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(preferredTheme);
    dom.queryInput.disabled = true;

    // Try to restore previous session
    const sessionRestored = await restoreSession();

    if (!sessionRestored) {
      renderFileList();
      setStatus('Sẵn sàng');
    }
  };

  init();
});
