async function postForm(form, btn) {
  const fd = new FormData(form);
  const btnText = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');
  const originalText = btnText.textContent;

  btn.disabled = true;
  btnText.textContent = 'Đang xử lý...';
  spinner.style.display = 'inline-block';

  try {
    const res = await fetch(form.action, { method: form.method || "POST", body: fd });
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (e) {
      throw new Error(`${res.status} ${res.statusText} – Response is not valid JSON:\n` + text.slice(0, 200));
    }
  } finally {
    btn.disabled = false;
    btnText.textContent = originalText;
    spinner.style.display = 'none';
  }
}

function $(sel) { return document.querySelector(sel); }

function setJSON(id, obj) {
  const el = $(id);
  if (el) {
    el.textContent = JSON.stringify(obj, null, 2);
    el.style.display = 'block';
  }
}

// ===== Upload =====
$('#upload-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const jsonOutput = $('#upload-json');
  jsonOutput.style.display = 'none';
  try {
    const data = await postForm(e.target, $('#btn-upload'));
    setJSON('#upload-json', data);
    if (data.session_id) {
      $('[name="session_id"]').value = data.session_id;
    }
  } catch (err) {
    setJSON('#upload-json', { error: String(err) });
  }
});

// ===== Ingest =====
$('#ingest-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const jsonOutput = $('#ingest-json');
  jsonOutput.style.display = 'none';
  try {
    const data = await postForm(e.target, $('#btn-ingest'));
    setJSON('#ingest-json', data);
  } catch (err) {
    setJSON('#ingest-json', { error: String(err) });
  }
});

// ===== Ask =====
$('#ask-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('#answer-box').style.display = 'none';
  $('#citations').style.display = 'none';
  $('#latency').textContent = '';

  try {
    const data = await postForm(e.target, $('#btn-ask'));

    const box = $('#answer-box');
    box.className = 'alert alert-success';
    box.style.display = 'block';
    box.innerHTML = data.answer || 'Không tìm thấy câu trả lời.';

    $('#latency').textContent = `Latency: ${data.latency_ms} ms | Confidence: ${(data.confidence * 100).toFixed(1)}%`;

    const tbody = $('#citations tbody');
    tbody.innerHTML = '';
    if (data.citations && data.citations.length > 0) {
      data.citations.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${c.doc}</td><td>${c.page}</td><td>${(c.score ?? 0).toFixed(3)}</td><td>${(c.text_span || '').replace(/</g, '&lt;')}</td>`;
        tbody.appendChild(tr);
      });
      $('#citations').style.display = 'table';
    }
  } catch (err) {
    const box = $('#answer-box');
    box.className = 'alert alert-danger';
    box.style.display = 'block';
    box.textContent = 'Lỗi: ' + err.message;
  }
});

// ===== Docs list =====
$('#btn-docs').addEventListener('click', async () => {
  const box = $('#docs-json');
  box.style.display = 'none';
  try {
    let res = await fetch('/rag-docs', { cache: 'no-store' });
    if (res.status === 404) res = await fetch('/docs', { cache: 'no-store' });
    const txt = await res.text();
    try {
      const data = JSON.parse(txt);
      setJSON('#docs-json', data);
    } catch {
      throw new Error('Response is not valid JSON: ' + txt.slice(0, 200));
    }
  } catch (e) {
    setJSON('#docs-json', { error: 'Lỗi tải danh sách: ' + e.message });
  }
});

// ===== Health check =====
fetch('/healthz').then(r => r.json()).then(d => $('#hz').textContent = d.status).catch(() => ($('#hz').textContent = 'down'));
