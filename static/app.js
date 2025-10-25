console.log('RAG PDF JavaScript loaded!');

document.addEventListener('DOMContentLoaded', () => {
  const dom = {
    themeToggle: document.getElementById('theme-toggle'),
    newSessionBtn: document.getElementById('btn-new-session'),
    chatList: document.getElementById('chat-list'),
    fileInput: document.getElementById('file-input'),
    fileUploader: document.getElementById('file-uploader'),
    fileList: document.getElementById('file-list'),
    ingestButton: document.getElementById('btn-ingest'),
    ocrSwitch: document.getElementById('ocr-switch'),
    queryInput: document.getElementById('query-input'),
    askButton: document.getElementById('btn-ask'),
    chatContainer: document.getElementById('chat-container'),
    docTitle: document.getElementById('doc-title'),
    sessionIdBadge: document.getElementById('session-id-badge'),
    sessionDocCount: document.getElementById('session-doc-count'),
    sessionChatCount: document.getElementById('session-chat-count'),
    knowledgeContent: document.getElementById('knowledge-content'),
    knowledgePlaceholder: document.getElementById('knowledge-placeholder'),
    citationsList: document.getElementById('citations-list'),
    statusIndicator: document.getElementById('status-indicator'),
    statusText: document.getElementById('status-text'),
    toastElement: document.getElementById('notification-toast'),
    // Modal elements
    renameModalEl: document.getElementById('renameModal'),
    renameInput: null,
    renameConfirmBtn: null,
    deleteModalEl: document.getElementById('deleteModal'),
    deleteConfirmBtn: null,
  };

  const bsToast = new bootstrap.Toast(dom.toastElement);

  if (window.marked) {
    marked.setOptions({
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false,
      highlight(code, lang) {
        if (window.hljs) {
          try {
            if (lang && hljs.getLanguage(lang)) {
              return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
          } catch (err) {
            console.warn('Highlight.js error:', err);
          }
        }
        return code;
      },
    });
  }

  // Initialize modal instances (after DOM loaded)
  const renameModal = dom.renameModalEl ? new bootstrap.Modal(dom.renameModalEl) : null;
  const deleteModal = dom.deleteModalEl ? new bootstrap.Modal(dom.deleteModalEl) : null;
  if (dom.renameModalEl) dom.renameInput = document.getElementById('rename-input');
  if (dom.renameModalEl) dom.renameConfirmBtn = document.getElementById('rename-confirm-btn');
  if (dom.deleteModalEl) dom.deleteConfirmBtn = document.getElementById('delete-confirm-btn');

  const WELCOME_HTML = `
        <div class="welcome-screen">
          <div class="welcome-icon">🤖</div>
          <h3>Trợ lý tài liệu RAG xin chào!</h3>
          <p>Hãy bắt đầu bằng cách tải lên tài liệu PDF của bạn ở thanh bên trái.</p>
          <div class="onboarding-steps">
            <div class="step"><span>1</span> Tải lên PDF</div>
            <div class="step"><span>2</span> Đặt câu hỏi</div>
            <div class="step"><span>3</span> Nhận câu trả lời &amp; trích dẫn</div>
          </div>
        </div>
      `;

  const createEmptyState = () => ({
    files: [],
    sessionId: null,
    isIngesting: false,
    isAsking: false,
    chats: {},
    activeChatId: null,
    sessions: [],
  });

  const generateSessionId = () => {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID();
    }
    return `session-${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`;
  };

  const sanitizeFilename = (name) => (name ? name.replace(/[^a-zA-Z0-9_.-]+/g, '_') : '');

  let state = createEmptyState();

  const SESSION_TTL_MS = 24 * 60 * 60 * 1000;

  const saveSessionToStorage = (sessionId) => {
    if (!sessionId) return;
    localStorage.setItem('rag_pdf_session_id', sessionId);
    localStorage.setItem('rag_pdf_session_timestamp', Date.now().toString());
  };

  const getSessionFromStorage = () => {
    const sessionId = localStorage.getItem('rag_pdf_session_id');
    const timestamp = localStorage.getItem('rag_pdf_session_timestamp');
    if (!sessionId || !timestamp) return null;
    if (Date.now() - parseInt(timestamp, 10) > SESSION_TTL_MS) {
      clearSessionFromStorage();
      return null;
    }
    return sessionId;
  };

  const clearSessionFromStorage = () => {
    localStorage.removeItem('rag_pdf_session_id');
    localStorage.removeItem('rag_pdf_session_timestamp');
  };

  const updateSessionMeta = () => {
    if (dom.sessionIdBadge) {
      if (state.sessionId) {
        dom.sessionIdBadge.textContent = `#${state.sessionId.slice(0, 8)}`;
        dom.sessionIdBadge.classList.remove('session-id-empty');
      } else {
        dom.sessionIdBadge.textContent = 'Chưa bắt đầu';
        dom.sessionIdBadge.classList.add('session-id-empty');
      }
    }

    if (dom.sessionDocCount) {
      const uploadedCount = state.files.filter((file) => ['uploaded', 'ingested'].includes(file.status)).length;
      const ingestedCount = state.files.filter((file) => file.status === 'ingested').length;
      let docLabel = '0 tài liệu';
      if (ingestedCount > 0) {
        docLabel = `${ingestedCount} tài liệu đã xử lý`;
      } else if (uploadedCount > 0) {
        docLabel = `${uploadedCount} tài liệu đã tải lên`;
      }
      dom.sessionDocCount.textContent = docLabel;
    }

    if (dom.sessionChatCount) {
      const chatCount = state.sessions.length;
      let chatLabel = '0 cuộc trò chuyện';
      if (chatCount === 1) {
        chatLabel = '1 cuộc trò chuyện';
      } else if (chatCount > 1) {
        chatLabel = `${chatCount} cuộc trò chuyện`;
      }
      dom.sessionChatCount.textContent = chatLabel;
    }
  };

  const upsertSessionSummary = (summary) => {
    if (!summary || !summary.session_id) return;
    const existingIndex = state.sessions.findIndex((s) => s.session_id === summary.session_id);
    const existing = existingIndex >= 0 ? state.sessions[existingIndex] : {};
    const hasDocsField = Object.prototype.hasOwnProperty.call(summary, 'docs');
    const mergedDocs = (() => {
      if (hasDocsField) return summary.docs || [];
      if (existing && existing.docs) return existing.docs;
      return [];
    })();
    const docCountValue = (() => {
      if (Object.prototype.hasOwnProperty.call(summary, 'doc_count')) {
        return summary.doc_count ?? (hasDocsField ? (summary.docs || []).length : mergedDocs.length);
      }
      if (hasDocsField) {
        return (summary.docs || []).length;
      }
      if (existing && Object.prototype.hasOwnProperty.call(existing, 'doc_count')) {
        return existing.doc_count ?? (existing.docs ? existing.docs.length : 0);
      }
      return mergedDocs.length;
    })();
    const normalized = {
      session_id: summary.session_id,
      title: summary.title ?? existing.title ?? 'Cuộc trò chuyện',
      created_at: summary.created_at ?? existing.created_at ?? null,
      updated_at: summary.updated_at ?? existing.updated_at ?? null,
      message_count: summary.message_count ?? existing.message_count ?? 0,
      chat_id: summary.chat_id ?? existing.chat_id ?? null,
      doc_count: docCountValue,
      docs: mergedDocs,
    };
    if (existingIndex >= 0) {
      state.sessions[existingIndex] = {
        ...state.sessions[existingIndex],
        ...normalized,
      };
    } else {
      state.sessions.push(normalized);
    }
    state.sessions.sort((a, b) => {
      const aUpdated = a.updated_at || 0;
      const bUpdated = b.updated_at || 0;
      return bUpdated - aUpdated;
    });
    updateSessionMeta();
  };

  const removeSessionSummary = (sessionId) => {
    if (!sessionId) return;
    state.sessions = state.sessions.filter((session) => session.session_id !== sessionId);
    updateSessionMeta();
  };

  const loadSessionsFromServer = async () => {
    try {
      const response = await fetch('/sessions');
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Không thể tải danh sách phiên làm việc');
      }
      state.sessions = (result.sessions || []).map((summary) => ({
        session_id: summary.session_id,
        title: summary.title || 'Cuộc trò chuyện',
        created_at: summary.created_at || null,
        updated_at: summary.updated_at || null,
        message_count: summary.message_count ?? 0,
        chat_id: summary.chat_id || null,
        doc_count: summary.doc_count ?? 0,
        docs: summary.docs || [],
      }));
      state.sessions.sort((a, b) => {
        const aUpdated = a.updated_at || 0;
        const bUpdated = b.updated_at || 0;
        return bUpdated - aUpdated;
      });
      updateSessionMeta();
      renderChatList();
    } catch (error) {
      console.error('Error loading sessions:', error);
      showToast(error.message, 'error');
    }
  };

  const mapServerFilesToState = (files = []) => files.map((file) => ({
    file: null,
    id: window.crypto?.randomUUID ? window.crypto.randomUUID() : `file-${Date.now()}-${Math.random()}`,
    status: file.status || 'ingested',
    serverDocName: file.name,
    size: file.size,
    pages: file.pages,
    chunks: file.chunks,
    name: file.orig_name || file.name,
    error: null,
  }));

  const setActiveSession = async (sessionId, { forceReload = false } = {}) => {
    if (!sessionId) return;
    const alreadyActive = state.sessionId === sessionId;
    state.sessionId = sessionId;
    saveSessionToStorage(sessionId);
    updateSessionMeta();

    if (alreadyActive && !forceReload) {
      renderChatList();
      return;
    }

    setStatus('Đang tải phiên làm việc...', 'processing');
    try {
      const response = await fetch(`/session/${sessionId}`);
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Không thể tải thông tin phiên làm việc');
      }

      state.files = mapServerFilesToState(result.files || []);
      renderFileList();

      const docNames = (result.files || []).map((f) => f.name).join(', ');
      dom.docTitle.textContent = docNames || '';

      const primaryChat = (result.chats || [])[0];
      const summary = {
        session_id: sessionId,
        title: primaryChat?.title || (state.sessions.find((s) => s.session_id === sessionId)?.title) || 'Cuộc trò chuyện',
        chat_id: primaryChat?.chat_id || null,
        message_count: primaryChat?.message_count ?? 0,
        updated_at: primaryChat?.updated_at ?? null,
        doc_count: (result.manifest?.docs || []).length,
        docs: result.manifest?.docs || [],
      };
      upsertSessionSummary(summary);

      rebuildChatState(result.chats || []);

      const chatId = primaryChat?.chat_id || summary.chat_id;
      if (chatId) {
        state.activeChatId = chatId;
        await setActiveChat(chatId, { reload: true });
      } else {
        state.activeChatId = null;
        resetChatUI();
      }

      const canAsk = result.can_ask ?? false;
      dom.askButton.disabled = !canAsk;
      dom.queryInput.disabled = !canAsk;
      dom.queryInput.placeholder = canAsk
        ? 'Bây giờ, hãy hỏi tôi điều gì đó...'
        : 'Hãy tải lên và xử lý tài liệu trước.';

      renderChatList();
    } catch (error) {
      console.error('Error setting active session:', error);
      showToast(error.message, 'error');
    } finally {
      setStatus('Sẵn sàng');
    }
  };

  const ensureSessionInitialized = async ({ silent = false } = {}) => {
    if (state.sessionId) return state.sessionId;
    if (!silent) setStatus('Đang tạo cuộc trò chuyện mới...', 'processing');
    try {
      const response = await fetch('/session', { method: 'POST' });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Không thể tạo cuộc trò chuyện mới');
      }

      if (result.session) {
        upsertSessionSummary(result.session);
      }

      state.chats = {};
      state.activeChatId = null;
      state.files = [];
      renderFileList();
      resetChatUI();

      await setActiveSession(result.session_id, { forceReload: true });
      if (!silent) {
        showToast('Đã tạo cuộc trò chuyện mới.', 'success');
      }
      return result.session_id;
    } catch (error) {
      showToast(error.message, 'error');
      throw error;
    } finally {
      if (!silent) setStatus('Sẵn sàng');
    }
  };

  const showToast = (message, type = 'info') => {
    dom.toastElement.querySelector('.toast-body').textContent = message;
    dom.toastElement.className = `toast ${type === 'error' ? 'bg-danger' : 'bg-success'}`;
    bsToast.show();
  };

  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
  };

  const setStatus = (text, type = 'ready') => {
    dom.statusText.textContent = text;
    dom.statusIndicator.className = `status-indicator-${type}`;
  };

  const applyTheme = (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    const icon = dom.themeToggle.querySelector('i');
    icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
  };

  const resetChatUI = () => {
    dom.chatContainer.innerHTML = WELCOME_HTML;
    dom.chatContainer.scrollTop = dom.chatContainer.scrollHeight;
    renderCitations([]);
  };

  const resetChatState = ({ preserveSessions = false } = {}) => {
    state.chats = {};
    state.activeChatId = null;
    if (!preserveSessions) {
      state.sessions = [];
    }
    renderChatList();
    resetChatUI();
    updateSessionMeta();
  };

  const syncChatMeta = (meta) => {
    if (!meta || !meta.chat_id) return;
    const previous = state.chats[meta.chat_id] || {};
    const messages = meta.messages !== undefined ? meta.messages : previous.messages || [];
    const messageCount = meta.message_count ?? messages.length;
    state.chats[meta.chat_id] = {
      ...previous,
      ...meta,
      messages,
      message_count: messageCount,
    };
    if (state.sessionId) {
      const currentSummary = state.sessions.find((session) => session.session_id === state.sessionId) || {};
      upsertSessionSummary({
        session_id: state.sessionId,
        title: meta.title || currentSummary.title || 'Cuộc trò chuyện',
        chat_id: meta.chat_id,
        message_count: messageCount,
        updated_at: meta.updated_at || currentSummary.updated_at || Date.now() / 1000,
        doc_count: currentSummary.doc_count,
        docs: currentSummary.docs,
      });
    }
  };

  const rebuildChatState = (chatArray = []) => {
    const existingMessages = {};
    Object.entries(state.chats).forEach(([id, chat]) => {
      existingMessages[id] = chat.messages || [];
    });
    state.chats = {};
    const limitedChats = chatArray.slice(0, 1);
    limitedChats.forEach((meta) => {
      const id = meta.chat_id;
      const messages = existingMessages[id] || [];
      state.chats[id] = {
        ...meta,
        messages,
        message_count: meta.message_count ?? messages.length,
      };
      if (state.sessionId) {
        const currentSummary = state.sessions.find((session) => session.session_id === state.sessionId) || {};
        upsertSessionSummary({
          session_id: state.sessionId,
          title: meta.title || currentSummary.title || 'Cuộc trò chuyện',
          chat_id: id,
          message_count: meta.message_count ?? messages.length,
          updated_at: meta.updated_at || currentSummary.updated_at,
          doc_count: currentSummary.doc_count,
          docs: currentSummary.docs,
        });
      }
    });
  };

  const renderChatList = () => {
    dom.chatList.innerHTML = '';
    if (state.sessions.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'chat-list-empty';
      empty.textContent = 'Chưa có cuộc trò chuyện nào';
      dom.chatList.appendChild(empty);
      updateSessionMeta();
      return;
    }

    state.sessions.forEach((sessionSummary) => {
      const chat = sessionSummary.chat_id ? state.chats[sessionSummary.chat_id] || {} : {};
      const sessionId = sessionSummary.session_id;
      const chatId = sessionSummary.chat_id;
      const item = document.createElement('div');
      item.className = `chat-item${sessionId === state.sessionId ? ' active' : ''}`;
      item.dataset.sessionId = sessionId;
      if (chatId) {
        item.dataset.chatId = chatId;
      }

      const content = document.createElement('div');
      content.className = 'chat-item-content';

      const titleSpan = document.createElement('span');
      titleSpan.className = 'chat-item-title';
      titleSpan.textContent = sessionSummary.title || chat.title || 'Cuộc trò chuyện';
      content.appendChild(titleSpan);

      const count = chat.messages ? chat.messages.length : sessionSummary.message_count || 0;
      const metaSpan = document.createElement('span');
      metaSpan.className = 'chat-item-meta';
      metaSpan.textContent = count > 0 ? `${count} tin nhắn` : 'Chưa có tin nhắn';
      content.appendChild(metaSpan);

      const actions = document.createElement('div');
      actions.className = 'chat-item-actions';

      const renameBtn = document.createElement('button');
      renameBtn.type = 'button';
      renameBtn.className = 'btn btn-icon btn-rename';
      renameBtn.dataset.action = 'rename';
      renameBtn.dataset.sessionId = sessionId;
      if (chatId) renameBtn.dataset.chatId = chatId;
      renameBtn.innerHTML = '<i class="bi bi-pencil"></i>';
      renameBtn.title = 'Đổi tên cuộc trò chuyện';

      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'btn btn-icon btn-delete';
      deleteBtn.dataset.action = 'delete';
      deleteBtn.dataset.sessionId = sessionId;
      if (chatId) deleteBtn.dataset.chatId = chatId;
      deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
      deleteBtn.title = 'Xoá cuộc trò chuyện';

      actions.append(renameBtn, deleteBtn);

      item.append(content, actions);
      dom.chatList.appendChild(item);
    });

    updateSessionMeta();
  };

  const sanitizeHtml = (html) => {
    if (window.DOMPurify) {
      return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
    }
    return html;
  };

  const enhanceMarkdownDom = (container) => {
    if (!container) return;

    container.querySelectorAll('a[href^="http"]').forEach((link) => {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    });

    const firstParagraph = container.querySelector('p');
    if (firstParagraph) {
      firstParagraph.classList.add('bubble-lead');
    }

    container.querySelectorAll('ul').forEach((list) => {
      list.classList.add('bubble-list');
      list.querySelectorAll('li').forEach((item) => {
        item.classList.add('bubble-list-item');
      });
    });

    container.querySelectorAll('ol').forEach((list) => {
      list.classList.add('bubble-ordered');
    });

    container.querySelectorAll('blockquote').forEach((quote) => {
      quote.classList.add('bubble-quote');
    });

    container.querySelectorAll('table').forEach((table) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'bubble-table-wrapper';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
      table.classList.add('table', 'table-striped', 'table-sm');
    });

    container.querySelectorAll('pre').forEach((pre) => {
      pre.classList.add('bubble-code-block');
    });

    container.querySelectorAll('code:not(pre code)').forEach((code) => {
      code.classList.add('bubble-inline-code');
    });

    if (window.hljs) {
      container.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
        if (!block.hasAttribute('tabindex')) {
          block.setAttribute('tabindex', '0');
        }
      });
    }

    container.querySelectorAll('.citation-ref[data-ref]').forEach((refEl) => {
      const refValue = refEl.dataset.ref;
      const citation = parseCitationToken(refValue);
      if (!citation) return;
      refEl.setAttribute('role', 'button');
      refEl.setAttribute('tabindex', '0');
      refEl.dataset.filename = citation.filename;
      refEl.dataset.page = citation.page ?? '';
      refEl.addEventListener('click', () => {
        highlightSourceReference(
          citation.filename,
          citation.pages && citation.pages.length ? citation.pages : citation.page,
        );
      });
      refEl.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          highlightSourceReference(
            citation.filename,
            citation.pages && citation.pages.length ? citation.pages : citation.page,
          );
        }
      });
    });
  };

  const buildMarkdownContent = (markdown) => {
    const raw = typeof marked !== 'undefined' ? marked.parse(markdown || '') : (markdown || '');
    let safeHtml = sanitizeHtml(raw || '');
    const citationPattern = /\[([^\[\]]+?\.pdf:\s*\d+(?:\s*(?:[-–,]\s*\d+)*)?)\]/gi;
    safeHtml = safeHtml.replace(citationPattern, (_match, token) => {
      const dataRef = String(token || '').replace(/"/g, '&quot;');
      return `<span class="citation-ref" data-ref="${dataRef}">[${token}]</span>`;
    });
    const container = document.createElement('div');
    container.className = 'bubble-content-body';
    container.innerHTML = safeHtml;
    enhanceMarkdownDom(container);
    return container;
  };

  const formatConfidence = (value) => {
    if (typeof value !== 'number' || Number.isNaN(value)) return null;
    const clamped = Math.max(0, Math.min(1, value));
    return `${Math.round(clamped * 100)}%`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return null;
    const isMillis = timestamp > 1e12;
    const date = new Date(isMillis ? timestamp : timestamp * 1000);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const createMetaPill = (label, value, type = 'default') => {
    const pill = document.createElement('span');
    pill.className = `meta-pill meta-pill-${type}`;
    pill.textContent = `${label}: ${value}`;
    return pill;
  };

  const createSourceChips = (sources) => {
    if (!Array.isArray(sources) || sources.length === 0) return null;

    const uniqueEntries = new Map();
    sources.forEach((source) => {
      if (!source || !source.filename) return;
      const filename = source.filename.trim();
      const pageValue = source.page === undefined || source.page === null
        ? ''
        : String(source.page).trim();
      const key = pageValue ? `${filename}:${pageValue}` : filename;
      if (!uniqueEntries.has(key)) {
        uniqueEntries.set(key, { filename, page: pageValue });
      }
    });

    if (uniqueEntries.size === 0) return null;

    const footer = document.createElement('div');
    footer.className = 'bubble-footer';
    const label = document.createElement('span');
    label.className = 'bubble-footer-label';
    label.textContent = 'Nguồn tham khảo:';
    footer.appendChild(label);

    const sortedKeys = Array.from(uniqueEntries.keys()).sort((a, b) => a.localeCompare(b));
    sortedKeys.forEach((key) => {
      const entry = uniqueEntries.get(key);
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'source-chip';
      chip.textContent = entry.page ? `${entry.filename}:${entry.page}` : entry.filename;
      chip.dataset.filename = entry.filename;
      chip.dataset.page = entry.page;
      chip.dataset.sourceKey = buildSourceKey(entry.filename, entry.page);
      chip.addEventListener('click', (evt) => {
        evt.preventDefault();
        evt.stopPropagation();
        highlightSourceReference(entry.filename, entry.page);
      });
      footer.appendChild(chip);
    });

    return footer;
  };

  const SOURCE_KEY_DELIMITER = '|';
  const HIGHLIGHT_DURATION = 1800;

  const escapeForSelector = (value = '') => {
    if (window.CSS && CSS.escape) {
      return CSS.escape(value);
    }
    return value.replace(/"/g, '\\"').replace(/\\/g, '\\\\');
  };

  const buildSourceKey = (filename, page) => {
    if (!filename) return null;
    return `${filename}:${page ?? ''}`;
  };

  const parseCitationToken = (value) => {
    if (!value) return null;
    const parts = value.split(':');
    const filename = parts[0]?.trim();
    if (!filename) return null;
    const pagePart = parts.slice(1).join(':').trim();
    const pages = [];

    if (pagePart) {
      pagePart
        .split(',')
        .map((segment) => segment.trim())
        .filter(Boolean)
        .forEach((segment) => {
          const rangeMatch = segment.match(/^(\d+)\s*[-–]\s*(\d+)$/);
          if (rangeMatch) {
            const [start, end] = rangeMatch.slice(1).map((n) => n.trim());
            if (start) pages.push(start);
            if (end) pages.push(end);
          } else {
            pages.push(segment);
          }
        });
    }

    return {
      filename,
      page: pages[0] || pagePart || '',
      pages,
      raw: pagePart,
    };
  };

  const parseSourceKeys = (value = '') =>
    value
      .split(SOURCE_KEY_DELIMITER)
      .map((part) => part.trim())
      .filter(Boolean);

  const pulseElement = (element, className) => {
    if (!element) return;
    element.classList.add(className);
    window.setTimeout(() => {
      element.classList.remove(className);
    }, HIGHLIGHT_DURATION);
  };

  const scrollElementIntoContainer = (container, element, { margin = 24 } = {}) => {
    if (!container || !element || typeof container.getBoundingClientRect !== 'function') {
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();

    const withinVertical =
      elementRect.top >= containerRect.top + margin &&
      elementRect.bottom <= containerRect.bottom - margin;
    if (withinVertical) {
      return;
    }

    const currentScrollTop =
      typeof container.scrollTop === 'number' ? container.scrollTop : 0;
    const targetTop =
      elementRect.top - containerRect.top + currentScrollTop - (containerRect.height - elementRect.height) / 2;
    const scrollTop = Math.max(0, targetTop);

    if (typeof container.scrollTo === 'function') {
      container.scrollTo({ top: scrollTop, behavior: 'smooth' });
    } else {
      container.scrollTop = scrollTop;
    }
  };

  const highlightSourceReference = (filename, pageOrPages) => {
    if (!filename) return;
    const rawPages = Array.isArray(pageOrPages) ? pageOrPages : [pageOrPages];
    const normalizedPages = rawPages
      .map((page) => (page === null || page === undefined ? '' : String(page).trim()))
      .filter((value, index, array) => array.indexOf(value) === index);

    if (normalizedPages.length === 0) {
      highlightSingleSource(filename, '', true);
      return;
    }

    let bubbleHighlighted = false;
    normalizedPages.forEach((page) => {
      const result = highlightSingleSource(filename, page, !bubbleHighlighted);
      if (result.bubbleHighlighted) {
        bubbleHighlighted = true;
      }
    });
  };

  const highlightSingleSource = (filename, page, highlightBubble) => {
    const escapedFilename = escapeForSelector(filename);
    const trimmedPage = page === null || page === undefined ? '' : String(page).trim();
    const escapedPage = escapeForSelector(trimmedPage);

    if (dom.citationsList) {
      const selector = trimmedPage
        ? `.citation-card[data-filename="${escapedFilename}"][data-page="${escapedPage}"]`
        : `.citation-card[data-filename="${escapedFilename}"]`;
      const cards = dom.citationsList.querySelectorAll(selector);
      const scrollContainer =
        dom.citationsList.closest('.knowledge-body') ||
        dom.knowledgeContent ||
        dom.citationsList;
      cards.forEach((card) => {
        scrollElementIntoContainer(scrollContainer, card, { margin: 40 });
        pulseElement(card, 'citation-highlight');
      });
    }

    let bubbleHighlighted = false;
    if (highlightBubble && dom.chatContainer) {
      const bubbles = Array.from(dom.chatContainer.querySelectorAll('.chat-bubble.ai'));
      const sourceKey = trimmedPage ? buildSourceKey(filename, trimmedPage) : null;
      const bubble = bubbles.find((node) => {
        const keys = parseSourceKeys(node.dataset.sourceKeys || '');
        if (sourceKey) {
          return keys.includes(sourceKey);
        }
        return keys.some((key) => key.startsWith(`${filename}:`));
      });
      if (bubble) {
        pulseElement(bubble, 'chat-highlight');
        bubbleHighlighted = true;
      }
    }

    return { bubbleHighlighted };
  };

  const toastCopyResult = (success) => {
    if (!dom.toastElement) return;
    if (success) {
      dom.toastElement.className = 'toast bg-success text-white';
      dom.toastElement.querySelector('.toast-body').textContent = 'Đã sao chép câu trả lời vào bộ nhớ tạm.';
    } else {
      dom.toastElement.className = 'toast bg-danger text-white';
      dom.toastElement.querySelector('.toast-body').textContent = 'Không thể sao chép. Vui lòng thử lại.';
    }
    bsToast.show();
  };

  const copyToClipboard = async (text) => {
    if (!text) return false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        toastCopyResult(true);
        return true;
      }
    } catch (err) {
      console.warn('Navigator clipboard API error:', err);
    }
    try {
      const textarea = document.createElement('textarea');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      toastCopyResult(success);
      return success;
    } catch (err) {
      console.warn('Fallback clipboard copy error:', err);
      toastCopyResult(false);
      return false;
    }
  };

  const createAssistantBubble = (message, index) => {
    const bubble = document.createElement('article');
    bubble.className = 'chat-bubble ai';

    const header = document.createElement('div');
    header.className = 'bubble-header';

    const headerTitle = document.createElement('div');
    headerTitle.className = 'bubble-title';
    headerTitle.innerHTML = '<i class="bi bi-stars"></i> Trợ lý RAG';
    header.appendChild(headerTitle);

    const meta = document.createElement('div');
    meta.className = 'bubble-meta';

    const confidenceText = formatConfidence(message.confidence);
    if (confidenceText) {
      meta.appendChild(createMetaPill('Độ tin cậy', confidenceText, 'confidence'));
    }

    const timeLabel = formatTimestamp(message.timestamp);
    if (timeLabel) {
      meta.appendChild(createMetaPill('Thời gian', timeLabel));
    }

    header.appendChild(meta);

    const actions = document.createElement('div');
    actions.className = 'bubble-actions';
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'btn btn-light btn-sm copy-answer-btn';
    copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Sao chép';
    copyBtn.dataset.copyText = message.content || '';
    actions.appendChild(copyBtn);
    header.appendChild(actions);

    bubble.appendChild(header);

    const contentWrapper = document.createElement('div');
    contentWrapper.className = 'bubble-content';
    const markdown = buildMarkdownContent(message.content || '');
    contentWrapper.appendChild(markdown);
    bubble.appendChild(contentWrapper);

    const sourcesFooter = createSourceChips(message.sources);
    if (sourcesFooter) {
      bubble.appendChild(sourcesFooter);
    }

    if (typeof index === 'number') {
      bubble.dataset.messageIndex = String(index);
    }
    if (message.timestamp) {
      bubble.dataset.timestamp = String(message.timestamp);
    }
    const sourceKeys = Array.isArray(message.sources)
      ? message.sources
        .map((src) => buildSourceKey(src.filename, src.page))
        .filter(Boolean)
        .join(SOURCE_KEY_DELIMITER)
      : '';
    if (sourceKeys) {
      bubble.dataset.sourceKeys = sourceKeys;
    }

    bubble.addEventListener('click', (event) => {
      const targetChip = event.target.closest('.source-chip');
      if (targetChip) {
        const chipPages = targetChip.dataset.pages
          ? targetChip.dataset.pages.split('|').map((p) => p.trim()).filter(Boolean)
          : [];
        highlightSourceReference(
          targetChip.dataset.filename,
          chipPages.length ? chipPages : targetChip.dataset.page,
        );
        return;
      }

      const copyButton = event.target.closest('.copy-answer-btn');
      if (copyButton) {
        copyToClipboard(message.content || '').catch((err) => {
          console.error('Copy failed:', err);
        });
        event.preventDefault();
        event.stopPropagation();
      }
    });

    return bubble;
  };

  const createUserBubble = (message, index) => {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.textContent = message.content || '';
    if (typeof index === 'number') {
      bubble.dataset.messageIndex = String(index);
    }
    if (message.timestamp) {
      bubble.dataset.timestamp = String(message.timestamp);
    }
    return bubble;
  };

  const createTypingBubble = () => {
    const bubble = document.createElement('article');
    bubble.className = 'chat-bubble ai bubble-loading';
    bubble.innerHTML = `
      <div class="bubble-content bubble-content-loading" role="status" aria-live="polite">
        <div class="typing-indicator">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <div class="typing-text">
          <span class="typing-label">Trợ lý đang suy nghĩ…</span>
          <span class="typing-hint">Đang tổng hợp thông tin phù hợp</span>
        </div>
      </div>
    `;
    return bubble;
  };

  const updateKnowledgePanel = (chat) => {
    if (!chat || !chat.messages || chat.messages.length === 0) {
      renderCitations([]);
      return;
    }
    for (let i = chat.messages.length - 1; i >= 0; i -= 1) {
      const message = chat.messages[i];
      if (message.role === 'assistant' && message.sources && message.sources.length) {
        renderCitations(message.sources);
        return;
      }
    }
    renderCitations([]);
  };

  const renderChatMessages = (chatId = state.activeChatId) => {
    const chat = chatId ? state.chats[chatId] : null;
    dom.chatContainer.innerHTML = '';

    if (!chat || !chat.messages || chat.messages.length === 0) {
      resetChatUI();
      return;
    }

    chat.messages.forEach((message, index) => {
      if (message.role === 'assistant') {
        dom.chatContainer.appendChild(createAssistantBubble(message, index));
      } else {
        dom.chatContainer.appendChild(createUserBubble(message, index));
      }
    });

    if (state.isAsking && chatId === state.activeChatId) {
      dom.chatContainer.appendChild(createTypingBubble());
    }

    dom.chatContainer.scrollTop = dom.chatContainer.scrollHeight;
    updateKnowledgePanel(chat);
  };

  const renderCitations = (sources) => {
    if (!sources || sources.length === 0) {
      dom.knowledgePlaceholder.style.display = 'block';
      dom.knowledgeContent.style.display = 'none';
      dom.citationsList.innerHTML = '';
      return;
    }

    dom.knowledgePlaceholder.style.display = 'none';
    dom.knowledgeContent.style.display = 'block';
    dom.citationsList.innerHTML = '';

    sources.forEach((source) => {
      const card = document.createElement('div');
      card.className = 'card citation-card';
      card.dataset.filename = source.filename;
      card.dataset.page = source.page;
      card.dataset.sourceKey = buildSourceKey(source.filename, source.page);
      card.tabIndex = 0;

      // Enhanced: Add status badge and age info
      const statusBadge = getStatusBadge(source.document_status);
      const ageInfo = getAgeInfo(source.upload_timestamp);
      const recencyBadge = source.recency_score ?
        `<span class="badge bg-info ms-1" title="Recency Score">📅 ${(source.recency_score * 100).toFixed(0)}%</span>` : '';

      card.innerHTML = `
          <div class="card-body">
            <h6 class="card-title">
              <span class="citation-tag" title="Click để xem chi tiết">${source.filename}:${source.page}</span>
              ${statusBadge}
              ${recencyBadge}
            </h6>
            <p class="card-text small">${source.content}</p>
            <div class="d-flex justify-content-between align-items-center">
              <small class="text-muted">${ageInfo}</small>
              <small class="text-muted">Mức khớp: ${formatScoreDisplay(source)}</small>
            </div>
          </div>`;
      const activate = (event) => {
        event.preventDefault();
        highlightSourceReference(source.filename, source.page);
      };
      card.addEventListener('click', activate);
      card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          activate(event);
        }
      });
      dom.citationsList.appendChild(card);
    });
  };

  // Helper functions for document status and age
  const getStatusBadge = (status) => {
    const badges = {
      'active': '<span class="badge bg-success ms-1" title="Tài liệu mới nhất">✨ Mới</span>',
      'superseded': '<span class="badge bg-warning text-dark ms-1" title="Đã được cập nhật">📝 Cũ</span>',
      'archived': '<span class="badge bg-secondary ms-1" title="Đã lưu trữ">📦 Archive</span>'
    };
    return badges[status] || '';
  };

  const getAgeInfo = (timestamp) => {
    if (!timestamp) return '';
    const now = Date.now() / 1000;
    const ageDays = Math.floor((now - timestamp) / 86400);

    if (ageDays === 0) return '📅 Hôm nay';
    if (ageDays === 1) return '📅 Hôm qua';
    if (ageDays < 7) return `📅 ${ageDays} ngày trước`;
    if (ageDays < 30) return `📅 ${Math.floor(ageDays / 7)} tuần trước`;
    if (ageDays < 365) return `📅 ${Math.floor(ageDays / 30)} tháng trước`;
    return `📅 ${Math.floor(ageDays / 365)} năm trước`;
  };

  const fetchChatMessages = async (chatId, { force = false } = {}) => {
    if (!state.sessionId || !chatId) return null;
    const existing = state.chats[chatId];
    if (!force && existing && existing.messages && existing.messages.length > 0) {
      return existing;
    }
    const response = await fetch(`/chat/${chatId}?session_id=${encodeURIComponent(state.sessionId)}`);
    const result = await response.json();
    if (!response.ok) {
      showToast(result.error || 'Không thể tải lịch sử cuộc trò chuyện', 'error');
      return null;
    }
    syncChatMeta(result.chat);
    return state.chats[chatId];
  };

  const setActiveChat = async (chatId, { reload = false } = {}) => {
    if (!chatId) return;
    state.activeChatId = chatId;
    if (!state.chats[chatId]) {
      state.chats[chatId] = { chat_id: chatId, title: 'Cuộc trò chuyện', messages: [] };
    }
    await fetchChatMessages(chatId, { force: reload });
    renderChatList();
    renderChatMessages(chatId);
  };

  const refreshChatListFromServer = async () => {
    if (!state.sessionId) return;
    const response = await fetch(`/chat/list?session_id=${encodeURIComponent(state.sessionId)}`);
    const result = await response.json();
    if (!response.ok) {
      showToast(result.error || 'Không thể lấy danh sách cuộc trò chuyện', 'error');
      return;
    }
    rebuildChatState(result.chats || []);
    renderChatList();
  };

  const ensureChatPresence = async ({ forceRefresh = false } = {}) => {
    if (!state.sessionId) return;
    const sessionSummary = state.sessions.find((session) => session.session_id === state.sessionId);
    if (forceRefresh || !sessionSummary || !sessionSummary.chat_id) {
      await refreshChatListFromServer();
    }
    const activeChatId = state.activeChatId && state.chats[state.activeChatId]
      ? state.activeChatId
      : (state.sessions.find((session) => session.session_id === state.sessionId)?.chat_id || null);
    if (activeChatId) {
      await setActiveChat(activeChatId, { reload: forceRefresh });
    }
  };

  const handleRenameSession = async (sessionId, chatId) => {
    if (!sessionId) return;
    // Open rename modal and prefill
    const summary = state.sessions.find((session) => session.session_id === sessionId) || {};
    const currentTitle = summary.title || (chatId ? state.chats[chatId]?.title : '') || '';
    if (!renameModal || !dom.renameInput || !dom.renameConfirmBtn) {
      // fallback to prompt
      const newTitle = prompt('Nhập tên cuộc trò chuyện', currentTitle);
      if (newTitle === null) return;
      const trimmed = newTitle.trim();
      if (!trimmed) {
        showToast('Tiêu đề không được để trống', 'error');
        return;
      }
      await performRename(sessionId, chatId, trimmed);
      return;
    }

    dom.renameInput.value = currentTitle;
    renameModal.show();

    const onConfirm = async () => {
      const trimmed = (dom.renameInput.value || '').trim();
      if (!trimmed) {
        showToast('Tiêu đề không được để trống', 'error');
        return;
      }
      dom.renameConfirmBtn.disabled = true;
      await performRename(sessionId, chatId, trimmed);
      dom.renameConfirmBtn.disabled = false;
      renameModal.hide();
      dom.renameConfirmBtn.removeEventListener('click', onConfirm);
    };

    dom.renameConfirmBtn.addEventListener('click', onConfirm);
  };

  const performRename = async (sessionId, chatId, newTitle) => {
    try {
      const formData = new FormData();
      formData.append('title', newTitle);
      if (chatId) {
        formData.append('chat_id', chatId);
      }
      const response = await fetch(`/session/${sessionId}/rename`, { method: 'POST', body: formData });
      const result = await response.json();
      if (!response.ok) {
        showToast(result.error || 'Không thể đổi tên cuộc trò chuyện', 'error');
        return;
      }
      if (result.session) {
        upsertSessionSummary(result.session);
        if (state.sessionId === sessionId && chatId) {
          await fetchChatMessages(chatId, { force: true });
          renderChatMessages(chatId);
        }
        renderChatList();
      }
      showToast('Đã đổi tên cuộc trò chuyện', 'success');
    } catch (err) {
      console.error('Rename error:', err);
      showToast(err.message || 'Lỗi khi đổi tên', 'error');
    }
  };

  const handleDeleteSession = async (sessionId) => {
    if (!sessionId) return;
    if (!deleteModal || !dom.deleteConfirmBtn) {
      // fallback to confirm
      if (!confirm('Bạn có chắc muốn xoá cuộc trò chuyện này?')) return;
      await performDelete(sessionId);
      return;
    }

    // show modal and attach handler
    const sessionSummary = state.sessions.find((s) => s.session_id === sessionId) || {};
    const title = sessionSummary.title || 'cuộc trò chuyện';
    const bodyEl = document.getElementById('delete-modal-body');
    if (bodyEl) bodyEl.textContent = `Bạn có chắc muốn xoá "${title}"? Hành động này không thể hoàn tác.`;
    deleteModal.show();

    const onDeleteConfirm = async () => {
      dom.deleteConfirmBtn.disabled = true;
      await performDelete(sessionId);
      dom.deleteConfirmBtn.disabled = false;
      deleteModal.hide();
      dom.deleteConfirmBtn.removeEventListener('click', onDeleteConfirm);
    };

    dom.deleteConfirmBtn.addEventListener('click', onDeleteConfirm);
  };

  const performDelete = async (sessionId) => {
    try {
      const response = await fetch(`/session/${sessionId}`, { method: 'DELETE' });
      const result = await response.json();
      if (!response.ok) {
        showToast(result.error || 'Không thể xoá cuộc trò chuyện', 'error');
        return;
      }
      removeSessionSummary(sessionId);
      if (state.sessionId === sessionId) {
        clearSessionFromStorage();
        resetChatState({ preserveSessions: true });
        state.sessionId = null;
        state.activeChatId = null;
        state.files = [];
        renderFileList();
        resetChatUI();
        const nextSession = state.sessions[0];
        if (nextSession) {
          await setActiveSession(nextSession.session_id);
        }
      }
      renderChatList();
      showToast('Đã xoá cuộc trò chuyện.', 'success');
    } catch (err) {
      console.error('Delete error:', err);
      showToast(err.message || 'Lỗi khi xoá cuộc trò chuyện', 'error');
    }
  };

  const renderFileList = () => {
    dom.fileList.innerHTML = '';
    if (state.files.length === 0) {
      dom.ingestButton.disabled = true;
      updateSessionMeta();
      return;
    }

    state.files.forEach((fileWrapper) => {
      const fileItem = document.createElement('div');
      fileItem.className = 'file-item';
      fileItem.dataset.id = fileWrapper.id;

      const fileName = fileWrapper.name || fileWrapper.file?.name || 'Unknown file';
      const fileSize = fileWrapper.size || fileWrapper.file?.size || 0;
      let statusIcon = '<i class="bi bi-file-earmark-arrow-up"></i>';
      if (fileWrapper.status === 'uploading') {
        statusIcon = '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>';
      } else if (fileWrapper.status === 'uploaded' || fileWrapper.status === 'ingested') {
        statusIcon = '<i class="bi bi-check-circle-fill text-success"></i>';
      } else if (fileWrapper.status === 'error') {
        statusIcon = '<i class="bi bi-x-circle-fill text-danger"></i>';
      }

      let statusLine = formatBytes(fileSize);
      if (fileWrapper.status === 'ingested' && fileWrapper.pages && fileWrapper.chunks) {
        statusLine = `${statusLine} • ${fileWrapper.pages} trang • ${fileWrapper.chunks} chunks`;
      } else if (fileWrapper.status === 'error' && fileWrapper.error) {
        statusLine = `${statusLine} • ${fileWrapper.error}`;
      }

      fileItem.innerHTML = `
        <div class="file-info">
          <div class="file-icon"><i class="bi bi-file-earmark-pdf-fill"></i></div>
          <div class="file-details">
            <div class="file-name" title="${fileName}">${fileName}</div>
            <div class="file-status">${statusLine}</div>
          </div>
        </div>
        <div class="file-actions">
          ${statusIcon}
          <button class="btn btn-icon btn-delete" data-id="${fileWrapper.id}" title="Xoá">
            <i class="bi bi-trash3"></i>
          </button>
        </div>`;
      dom.fileList.appendChild(fileItem);
    });

    const hasUploaded = state.files.some((f) => f.status === 'uploaded');
    const hasIngested = state.files.some((f) => f.status === 'ingested');
    dom.ingestButton.disabled = !hasUploaded;
    if (hasIngested && !hasUploaded) {
      dom.ingestButton.textContent = '✓ Đã xử lý';
      dom.ingestButton.disabled = true;
    } else {
      dom.ingestButton.innerHTML = '<i class="bi bi-gear"></i> Xử lý & Vector hóa';
    }

    updateSessionMeta();
  };

  const handleFiles = async (files) => {
    const newFiles = Array.from(files)
      .filter((file) => (file.type && file.type.toLowerCase().includes('pdf')) || file.name.toLowerCase().endsWith('.pdf'))
      .map((file) => ({ file, id: `file-${Date.now()}-${Math.random()}`, status: 'pending' }));
    if (newFiles.length === 0) return;
    await ensureSessionInitialized({ silent: true });
    state.files.push(...newFiles);
    renderFileList();
    uploadFiles();
  };

  const uploadFiles = async () => {
    const pendingFiles = state.files.filter((f) => f.status === 'pending');
    if (pendingFiles.length === 0) return;

    const formData = new FormData();
    if (state.sessionId) formData.append('session_id', state.sessionId);
    pendingFiles.forEach((fw) => {
      fw.status = 'uploading';
      formData.append('files', fw.file);
    });
    renderFileList();

    let response;
    let result;
    try {
      response = await fetch('/upload', { method: 'POST', body: formData });
      result = await response.json();
    } catch (networkError) {
      pendingFiles.forEach((fw) => {
        fw.status = 'error';
        fw.error = 'Mất kết nối khi tải lên';
      });
      renderFileList();
      showToast(`Lỗi tải lên: ${networkError.message}`, 'error');
      return;
    }

    const markErrors = (errorsList) => {
      if (!Array.isArray(errorsList)) return 0;
      let count = 0;
      errorsList.forEach((err) => {
        const name = err.file || '';
        const reason = err.error || 'Lỗi không xác định';
        const sanitizedName = sanitizeFilename(name);
        const match = state.files.find(
          (fw) => fw.status === 'uploading' && fw.file && fw.file.name === name,
        ) || state.files.find(
          (fw) => fw.status === 'uploading' && fw.file && name && fw.file.name.toLowerCase() === name.toLowerCase(),
        ) || state.files.find(
          (fw) => fw.status === 'uploading' && fw.serverDocName === sanitizedName,
        );
        const target = match || state.files.find((fw) => fw.status === 'uploading' && !fw.serverDocName);
        if (target) {
          target.status = 'error';
          target.error = reason;
          count += 1;
        }
      });
      return count;
    };

    if (!response.ok) {
      const errorCount = markErrors(result?.errors);
      if (errorCount === 0) {
        pendingFiles.forEach((fw) => {
          if (fw.status === 'uploading') {
            fw.status = 'error';
            fw.error = result?.error || 'Upload thất bại';
          }
        });
      }
      renderFileList();
      showToast(`Lỗi tải lên: ${result?.error || 'Upload failed'}`, 'error');
      return;
    }

    state.sessionId = result.session_id;
    saveSessionToStorage(state.sessionId);

    const errorCount = markErrors(result.errors);
    let uploadedCount = 0;
    result.files.forEach((uploadedFile) => {
      const serverName = uploadedFile.orig_name || uploadedFile.name;
      const serverSize = uploadedFile.size;
      const match = state.files.find(
        (fw) => fw.status === 'uploading' && (fw.file.name === serverName || fw.file.size === serverSize),
      );
      if (match) {
        match.status = 'uploaded';
        match.serverDocName = uploadedFile.name;
        delete match.error;
        uploadedCount += 1;
      }
    });

    if (uploadedCount > 0 && errorCount === 0) {
      showToast(`Đã tải lên thành công ${uploadedCount} file.`, 'success');
    } else if (uploadedCount > 0 && errorCount > 0) {
      showToast(`Tải thành công ${uploadedCount} file, ${errorCount} file lỗi.`, 'info');
    } else if (uploadedCount === 0 && errorCount > 0) {
      showToast('Toàn bộ file tải lên đều lỗi.', 'error');
    }

    if (uploadedCount > 0) {
      try {
        await ensureChatPresence({ forceRefresh: true });
      } catch (err) {
        console.error('Không thể đồng bộ chat sau khi upload:', err);
      }
    }

    renderFileList();
  };

  dom.fileUploader.addEventListener('click', (event) => {
    if (event.target.tagName !== 'LABEL') {
      dom.fileInput.click();
    }
  });

  dom.fileInput.addEventListener('change', (event) => {
    handleFiles(event.target.files).catch((error) => {
      console.error('File handling error:', error);
      showToast(error.message, 'error');
    });
  });

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((name) => {
    dom.fileUploader.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
  });

  dom.fileUploader.addEventListener('dragover', () => dom.fileUploader.classList.add('drag-over'));
  dom.fileUploader.addEventListener('dragleave', () => dom.fileUploader.classList.remove('drag-over'));
  dom.fileUploader.addEventListener('drop', (event) => {
    handleFiles(event.dataTransfer.files).catch((error) => {
      console.error('File handling error:', error);
      showToast(error.message, 'error');
    });
  });

  dom.fileList.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-id]');
    if (!button) return;
    const fileEntry = state.files.find((fw) => fw.id === button.dataset.id);
    if (!fileEntry) return;

    const isUploaded = ['uploaded', 'ingested'].includes(fileEntry.status) && fileEntry.serverDocName;
    if (!isUploaded || !state.sessionId) {
      state.files = state.files.filter((fw) => fw.id !== button.dataset.id);
      renderFileList();
      return;
    }

    setStatus('Đang xoá tài liệu...', 'processing');
    try {
      const encodedName = encodeURIComponent(fileEntry.serverDocName);
      const response = await fetch(`/session/${state.sessionId}/file/${encodedName}`, { method: 'DELETE' });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Không thể xoá tài liệu');
      }

      if (result.session) {
        const snapshot = result.session;
        const serverFiles = mapServerFilesToState(snapshot.files || []);
        const localOnly = state.files.filter(
          (fw) => (!fw.serverDocName || fw.status === 'pending' || fw.status === 'uploading') && fw.id !== fileEntry.id,
        );
        state.files = [...localOnly, ...serverFiles];
        dom.docTitle.textContent = state.files.map((f) => f.serverDocName || f.name).join(', ');
        renderFileList();

        upsertSessionSummary({
          session_id: state.sessionId,
          doc_count: snapshot.manifest?.docs?.length ?? 0,
          docs: snapshot.manifest?.docs ?? [],
        });

        dom.askButton.disabled = !snapshot.can_ask;
        dom.queryInput.disabled = !snapshot.can_ask;
        dom.queryInput.placeholder = snapshot.can_ask
          ? 'Bây giờ, hãy hỏi tôi điều gì đó...'
          : 'Hãy tải lên và xử lý tài liệu trước.';

        rebuildChatState(snapshot.chats || []);
        renderChatList();
        if (state.activeChatId) {
          await fetchChatMessages(state.activeChatId, { force: true });
          renderChatMessages(state.activeChatId);
        }
      }

      showToast('Đã xoá tài liệu và cập nhật dữ liệu liên quan.', 'success');
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setStatus('Sẵn sàng');
    }
  });

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

      result.ingested.forEach((ingested) => {
        const fileWrapper = state.files.find((fw) => fw.serverDocName === ingested.doc);
        if (fileWrapper) {
          fileWrapper.status = 'ingested';
          fileWrapper.pages = ingested.pages;
          fileWrapper.chunks = ingested.chunks;
        }
      });

      if (Array.isArray(result.docs)) {
        result.docs.forEach((doc) => {
          const fileWrapper = state.files.find((fw) => fw.serverDocName === (doc.doc || doc.name));
          if (fileWrapper) {
            fileWrapper.pages = doc.pages ?? fileWrapper.pages;
            fileWrapper.chunks = doc.chunks ?? fileWrapper.chunks;
            if (fileWrapper.status !== 'ingested') {
              fileWrapper.status = 'ingested';
            }
          }
        });
      }

      renderFileList();
      dom.askButton.disabled = false;
      dom.queryInput.disabled = false;
      dom.queryInput.placeholder = 'Bây giờ, hãy hỏi tôi điều gì đó...';
      const docListForTitle = (Array.isArray(result.docs) && result.docs.length > 0)
        ? result.docs
        : result.ingested;
      if (docListForTitle.length > 0) {
        dom.docTitle.textContent = docListForTitle
          .map((d) => d.doc || d.name)
          .filter(Boolean)
          .join(', ');
      }
      if (Array.isArray(result.docs)) {
        upsertSessionSummary({
          session_id: state.sessionId,
          doc_count: result.docs.length,
          docs: result.docs,
        });
      } else {
        const existingSummary = state.sessions.find((session) => session.session_id === state.sessionId) || { docs: [] };
        const existingDocsByName = new Map((existingSummary.docs || []).map((doc) => [doc.doc || doc.name, doc]));
        result.ingested.forEach((doc) => {
          existingDocsByName.set(doc.doc, doc);
        });
        const mergedDocs = Array.from(existingDocsByName.values());
        upsertSessionSummary({
          session_id: state.sessionId,
          doc_count: mergedDocs.length,
          docs: mergedDocs,
        });
      }
      saveSessionToStorage(state.sessionId);
      if (result.message) {
        showToast(result.message, result.total_chunks > 0 ? 'success' : 'info');
      } else {
        showToast(`Đã xử lý thành công ${result.total_chunks} chunks từ ${result.ingested.length} tài liệu.`, 'success');
      }
      await ensureChatPresence();
    } catch (error) {
      showToast(`Lỗi xử lý: ${error.message}`, 'error');
    } finally {
      state.isIngesting = false;
      dom.ingestButton.disabled = state.files.every((f) => f.status !== 'uploaded');
      setStatus('Sẵn sàng');
    }
  });

  const handleAsk = async () => {
    const query = dom.queryInput.value.trim();
    if (!query || state.isAsking) return;
    if (!state.sessionId) {
      showToast('Vui lòng tải lên và xử lý tài liệu trước khi hỏi.', 'error');
      return;
    }
    await ensureChatPresence();
    if (!state.activeChatId) {
      showToast('Không thể tạo cuộc trò chuyện mới. Vui lòng thử lại.', 'error');
      return;
    }

    dom.queryInput.value = '';
    dom.askButton.disabled = true;
    state.isAsking = true;
    setStatus('AI đang suy nghĩ...', 'processing');

    const chat = state.chats[state.activeChatId] || { chat_id: state.activeChatId, messages: [] };
    chat.messages = chat.messages || [];
    chat.messages.push({ role: 'user', content: query, timestamp: Date.now() });
    state.chats[state.activeChatId] = chat;
    renderChatMessages(state.activeChatId);

    try {
      const formData = new FormData();
      formData.append('query', query);
      formData.append('session_id', state.sessionId);
      formData.append('chat_id', state.activeChatId);

      const response = await fetch('/ask', { method: 'POST', body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Ask failed');

      if (result.chat) {
        syncChatMeta(result.chat);
      }

      await fetchChatMessages(state.activeChatId, { force: true });
      renderChatList();
    } catch (error) {
      const chatRef = state.chats[state.activeChatId];
      if (chatRef) {
        chatRef.messages.push({
          role: 'assistant',
          content: `Rất tiếc, đã có lỗi xảy ra: ${error.message}`,
          timestamp: Date.now(),
          sources: [],
        });
      }
      showToast(error.message, 'error');
    } finally {
      state.isAsking = false;
      dom.askButton.disabled = false;
      setStatus('Sẵn sàng');
      if (state.activeChatId) {
        renderChatMessages(state.activeChatId);
      } else {
        resetChatUI();
      }
    }
  };

  const restoreSession = async () => {
    const savedSessionId = getSessionFromStorage();
    if (savedSessionId) {
      try {
        await setActiveSession(savedSessionId, { forceReload: true });
        showToast('Đã khôi phục cuộc trò chuyện gần nhất.', 'success');
        setStatus('Đã khôi phục phiên làm việc', 'ready');
        return true;
      } catch (error) {
        console.error('Unable to restore saved session:', error);
        clearSessionFromStorage();
      }
    }
    if (state.sessions.length > 0) {
      await setActiveSession(state.sessions[0].session_id, { forceReload: false });
      return true;
    }
    return false;
  };

  const startNewSession = async () => {
    setStatus('Đang tạo cuộc trò chuyện mới...', 'processing');
    try {
      state.sessionId = null;
      await ensureSessionInitialized({ silent: true });
      showToast('Đã tạo cuộc trò chuyện mới.', 'success');
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      setStatus('Sẵn sàng');
    }
  };

  dom.themeToggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });

  dom.newSessionBtn.addEventListener('click', startNewSession);

  dom.chatList.addEventListener('click', async (event) => {
    const actionButton = event.target.closest('button[data-action]');
    if (actionButton) {
      const { action, sessionId, chatId } = actionButton.dataset;
      if (action === 'rename') {
        await handleRenameSession(sessionId, chatId);
      } else if (action === 'delete') {
        await handleDeleteSession(sessionId);
      }
      event.stopPropagation();
      return;
    }
    const item = event.target.closest('.chat-item');
    if (item?.dataset.sessionId) {
      await setActiveSession(item.dataset.sessionId);
    }
  });

  dom.askButton.addEventListener('click', handleAsk);
  dom.queryInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleAsk();
    }
  });

  const init = async () => {
    const preferredTheme = localStorage.getItem('theme')
      || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(preferredTheme);
    dom.queryInput.disabled = true;
    resetChatUI();
    updateSessionMeta();
    await loadSessionsFromServer();
    const restored = await restoreSession();
    if (!restored) {
      renderFileList();
      setStatus('Sẵn sàng');
    }
  };

  init();
});
const formatScoreDisplay = (source) => {
  if (!source || typeof source !== 'object') return '';
  const relevance = Number(source.relevance);
  if (!Number.isNaN(relevance) && relevance > 0) {
    return `${Math.round(Math.min(relevance, 1) * 100)}%`;
  }
  const score = Number(source.score);
  if (!Number.isNaN(score) && Number.isFinite(score)) {
    return score.toFixed(3);
  }
  return '';
};
