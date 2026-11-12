/*
 * 화면 흐름: 1. 파일 올리기 → 2. 제작 사이즈 입력 → [확인하기] → 3. 결과
 */
(function () {
  'use strict';

  const S = window.SETTINGS;
  const M = window.MESSAGES;
  const fmt = window.Ratio.fmt;
  const $ = (id) => document.getElementById(id);

  const ITEM_KEYS = ['standee', 'banner', 'print', 'poster', 'etc'];
  const state = { file: null, item: null, checked: null };

  /* {w} 같은 자리에 값 넣기 */
  function t(key, vars) {
    let s = M[key] || '';
    if (vars) Object.keys(vars).forEach(function (k) { s = s.split('{' + k + '}').join(vars[k]); });
    return s;
  }

  /* ---------- 초기 화면 ---------- */
  function initTexts() {
    document.documentElement.style.setProperty('--brand', S.brandColor || '#000');
    $('brand').textContent = S.companyName || '';
    $('title').textContent = M.title;
    $('intro').textContent = M.intro;
    $('privacy').textContent = M.privacy;
    document.querySelectorAll('[data-msg]').forEach(function (el) { el.textContent = M[el.dataset.msg] || ''; });
    $('foot').textContent = S.companyName ? '© ' + S.companyName : '';

    const box = $('items');
    ITEM_KEYS.forEach(function (key) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', 'false');
      b.dataset.item = key;
      b.textContent = M.items[key];
      b.addEventListener('click', function () { selectItem(key); });
      box.appendChild(b);
    });

    const zl = $('zoomLevels');
    S.zoomLevels.forEach(function (z) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.setAttribute('role', 'radio');
      b.dataset.zoom = z;
      b.textContent = z + '%';
      b.addEventListener('click', function () { setZoom(z); });
      zl.appendChild(b);
    });
    markZoom(S.defaultZoom);
  }

  /* ---------- 4. 확대 화질 보기 ---------- */
  let viewer = null;

  function markZoom(z) {
    document.querySelectorAll('#zoomLevels .chip').forEach(function (b) {
      b.setAttribute('aria-checked', String(Number(b.dataset.zoom) === z));
    });
  }

  function setZoom(z) {
    markZoom(z);
    viewer.setZoom(z);
  }

  function openZoom() {
    if (!state.file || !state.checked) return;
    const c = state.checked;
    $('step4').hidden = false;
    $('zoomDesc').textContent = t('zoomDesc', { w: fmt(c.w), h: fmt(c.h) });

    const qb = $('quality');
    if (S.showQualityBadge) {
      const q = window.ZoomViewer.quality(state.file, c.w, c.h, c.item, S);
      qb.className = 'quality ' + q.level;
      $('qualityText').textContent = M[{ good: 'qualityGood', ok: 'qualityOk', low: 'qualityLow', pdf: 'qualityPdf' }[q.level]];
      qb.hidden = false;
    } else {
      qb.hidden = true;
    }
    showUpscale(window.ZoomViewer.quality(state.file, c.w, c.h, c.item, S).level);

    viewer.setSource(state.file, c.w, c.h);
    $('step4').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* 화질이 낮으면 '무료 화질 개선 신청' 버튼 보여주기 */
  function showUpscale(level) {
    const box = $('upscale');
    const levels = S.upscaleOfferFor || ['low'];
    box.hidden = levels.indexOf(level) < 0;
    $('upEmail').textContent = S.upscaleEmail || '';
  }

  /* 글자 복사 (안 되는 브라우저는 예전 방식으로 한 번 더 시도) */
  function copyText(text) {
    return new Promise(function (resolve) {
      const legacy = function () {
        try {
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.setAttribute('readonly', '');
          ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          const ok = document.execCommand('copy');
          document.body.removeChild(ta);
          resolve(ok);
        } catch (e) { resolve(false); }
      };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { resolve(true); }, legacy);
        } else legacy();
      } catch (e) { legacy(); }
    });
  }

  function openMailModal() {
    const email = S.upscaleEmail || '';
    copyText(email).then(function (ok) {
      const title = $('mailModalTitle');
      title.textContent = ok ? '✅ ' + M.mailCopied : M.mailCopyFailed;
      title.classList.toggle('fail', !ok);
      $('modalEmail').textContent = email;
      $('mailModal').hidden = false;
      document.body.style.overflow = 'hidden';
      $('mailModalClose').focus();
    });
  }

  function closeMailModal() {
    $('mailModal').hidden = true;
    document.body.style.overflow = '';
    $('mailCopyBtn').focus();
  }

  function selectItem(key) {
    state.item = key;
    document.querySelectorAll('#items .chip').forEach(function (b) {
      b.setAttribute('aria-checked', String(b.dataset.item === key));
    });
    markStale();
  }

  /* 직원이 보낸 링크로 미리 채우기: ?item=standee&w=60&h=180 */
  function applyUrlParams() {
    const p = new URLSearchParams(location.search);
    const item = p.get('item');
    if (item && ITEM_KEYS.indexOf(item) >= 0) selectItem(item);
    if (p.get('w')) $('reqW').value = p.get('w');
    if (p.get('h')) $('reqH').value = p.get('h');
  }

  /* ---------- 1. 파일 올리기 ---------- */
  function showFileError(msg) {
    const el = $('fileError');
    el.textContent = msg;
    el.hidden = !msg;
  }

  async function handleFile(file) {
    if (!file) return;
    showFileError('');
    $('loading').hidden = false;
    $('original').hidden = true;
    $('drop').classList.add('has-file');
    hideResult();

    try {
      const info = await window.PrintFile.load(file, S);
      if (state.file && state.file.objectUrl) URL.revokeObjectURL(state.file.objectUrl);
      if (state.file && state.file.pdf && state.file.pdf !== info.pdf) state.file.pdf.destroy();
      state.file = info;
      showOriginal(info);
    } catch (e) {
      state.file = null;
      $('drop').classList.remove('has-file');
      const map = { tooLarge: M.tooLarge, unsupported: M.unsupported, aiOld: M.aiOld, password: M.password, broken: M.broken };
      showFileError(map[e.code] || M.broken);
      if (!e.code) console.error(e);
    } finally {
      $('loading').hidden = true;
      $('fileInput').value = '';
    }
  }

  function showOriginal(info) {
    $('thumb').src = info.thumb.toDataURL('image/jpeg', 0.9);
    $('fileName').textContent = info.name;
    const pick = $('pagePick'), sel = $('pageSelect');
    if (info.type === 'pdf' && info.pageCount > 1) {
      if (sel.options.length !== info.pageCount || sel.dataset.file !== info.name) {
        sel.innerHTML = '';
        for (let i = 1; i <= info.pageCount; i++) {
          const o = document.createElement('option');
          o.value = i; o.textContent = t('pageOption', { n: i });
          sel.appendChild(o);
        }
        sel.dataset.file = info.name;
      }
      sel.value = info.pageNum;
      pick.hidden = false;
    } else {
      pick.hidden = true;
    }
    const el = $('origSize');
    if (info.hasSize) {
      el.textContent = t('originalSize', { w: fmt(info.cmW), h: fmt(info.cmH) });
      el.classList.remove('ratio-only');
    } else {
      const r = window.Ratio.simpleRatio(info.ratioW, info.ratioH);
      el.textContent = t('originalRatioOnly', { w: r.w, h: r.h });
      el.classList.add('ratio-only');
    }
    $('original').hidden = false;
  }

  /* PDF 페이지 바꾸기 */
  async function changePage(n) {
    const cur = state.file;
    if (!cur || cur.type !== 'pdf') return;
    $('loading').hidden = false;
    hideResult();
    try {
      const info = await window.PrintFile.loadPdfPage(cur.pdf, n, cur.name);
      state.file = info;
      showOriginal(info);
    } catch (e) {
      showFileError(M.broken);
    } finally {
      $('loading').hidden = true;
    }
  }

  /* ---------- 2. 제작 사이즈 → 확인하기 ---------- */
  function parseCm(raw) {
    const s = String(raw).trim().replace(/cm$/i, '').trim();
    if (s === '') return { empty: true };
    if (!/^\d+(\.\d+)?$|^\.\d+$/.test(s)) return { bad: true };
    const n = parseFloat(s);
    if (!(n > 0)) return { bad: true };
    return { value: n };
  }

  function showSizeError(msg) {
    const el = $('sizeError');
    el.textContent = msg;
    el.hidden = !msg;
  }

  function onCheck() {
    showSizeError('');
    const w = parseCm($('reqW').value);
    const h = parseCm($('reqH').value);
    if (w.empty || h.empty) return showSizeError(M.errorEmpty);
    if (w.bad || h.bad) return showSizeError(M.errorNumber);
    if (!state.file) return showSizeError(M.needFileFirst);

    state.checked = { w: w.value, h: h.value, item: state.item || 'etc' };
    renderResult();
  }

  function markStale() {
    if (!$('step3').hidden) $('stale').hidden = false;
  }

  function hideResult() {
    $('step3').hidden = true;
    $('step4').hidden = true;
    state.checked = null;
  }

  /* ---------- 3. 결과 ---------- */
  function drawInto(canvas, src, aspect, maxW, maxH) {
    let w = maxW, h = maxW / aspect;
    if (h > maxH) { h = maxH; w = maxH * aspect; }
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    canvas.style.width = Math.round(w) + 'px';
    canvas.style.height = Math.round(h) + 'px';
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);   // 입력 비율로 강제로 늘려 그림
  }

  function renderResult(noScroll) {
    const f = state.file, c = state.checked;
    const j = window.Ratio.judge(f.ratioW, f.ratioH, c.w, c.h, S.ratioTolerancePercent);

    $('step3').hidden = false;
    $('stale').hidden = true;
    $('step4').hidden = true;

    const stageW = $('previews').clientWidth || 300;
    const maxH = Math.min(380, window.innerHeight * 0.5);
    const reqAspect = c.w / c.h;

    $('pvMainCap').textContent = j.ok ? '' : M.previewStretched;
    $('pvMainCap').hidden = j.ok;
    $('pvMainSize').textContent = fmt(c.w) + ' × ' + fmt(c.h) + 'cm';

    if (j.ok) {
      $('pvOrigWrap').hidden = true;
      drawInto($('pvMain'), f.thumb, reqAspect, stageW - 24, maxH);
    } else {
      $('pvOrigWrap').hidden = false;
      const gap = 12, mainW = (stageW - gap) * 2 / 3 - 20, origW = (stageW - gap) / 3 - 20;
      drawInto($('pvMain'), f.thumb, reqAspect, mainW, maxH);
      drawInto($('pvOrig'), f.thumb, f.ratioW / f.ratioH, origW, maxH * 0.6);
    }

    const v = $('verdict');
    v.innerHTML = '';
    if (j.ok) {
      const box = el('div', 'box ok', t('ratioOk', { w: fmt(c.w), h: fmt(c.h) }));
      v.appendChild(box);
    } else {
      const pct = Math.max(1, Math.round(j.diffPercent));
      const box = el('div', 'box warn');
      box.appendChild(el('strong', '', M.ratioBadTitle));
      box.appendChild(el('span', '', t(j.wider ? 'ratioWider' : 'ratioNarrower', { p: pct })));
      v.appendChild(box);

      const fit = el('div', 'fit');
      fit.appendChild(el('p', '', M.fitTitle));
      const ul = el('ul');
      ul.appendChild(el('li', '', t('fitByHeight', { h: fmt(j.fitByHeight.h), w: fmt(j.fitByHeight.w) })));
      ul.appendChild(el('li', '', t('fitByWidth', { w: fmt(j.fitByWidth.w), h: fmt(j.fitByWidth.h) })));
      fit.appendChild(ul);
      v.appendChild(fit);
    }

    if (!noScroll) $('step3').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* ---------- 이벤트 연결 ---------- */
  function bind() {
    $('fileInput').addEventListener('change', function (e) { handleFile(e.target.files[0]); });
    $('changeFile').addEventListener('click', function () { $('fileInput').click(); });

    const drop = $('drop');
    ['dragenter', 'dragover'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      drop.addEventListener(ev, function () { drop.classList.remove('over'); });
    });
    drop.addEventListener('drop', function (e) {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    });
    // 페이지 아무 데나 떨어뜨려도 브라우저가 파일을 열어버리지 않게
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('drop', function (e) { e.preventDefault(); });

    $('checkBtn').addEventListener('click', onCheck);
    $('zoomBtn').addEventListener('click', openZoom);
    $('mailCopyBtn').addEventListener('click', openMailModal);
    $('mailModalClose').addEventListener('click', closeMailModal);
    $('mailModalBg').addEventListener('click', closeMailModal);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !$('mailModal').hidden) closeMailModal(); });
    $('pageSelect').addEventListener('change', function (e) { changePage(Number(e.target.value)); });
    ['reqW', 'reqH'].forEach(function (id) {
      $(id).addEventListener('input', markStale);
      $(id).addEventListener('keydown', function (e) { if (e.key === 'Enter') onCheck(); });
    });

    let resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (state.checked && $('stale').hidden) {
          const zoomOpen = !$('step4').hidden;
          renderResult(true);
          if (zoomOpen) { $('step4').hidden = false; viewer.draw(); }
        }
      }, 200);
    });
  }

  initTexts();
  viewer = new window.ZoomViewer({ canvas: $('zoomCanvas'), minimap: $('minimap'), settings: S });
  bind();
  applyUrlParams();
})();
