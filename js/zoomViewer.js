/*
 * 확대 화질 보기 (돋보기 창 + 미니맵)
 *
 * 일러스트레이터 방식(mode: "illustrator"):
 *   100%일 때 출력물 1인치 = 화면 72px(screenPpi). 제작 사이즈로 늘린 그림을 기준으로 확대.
 *   화면 px / 출력 1cm = (screenPpi ÷ 2.54) × (배율 ÷ 100)
 * 포토샵 방식(mode: "photoshop"):
 *   100%일 때 원본 1px = 화면 1px. 제작 사이즈와 무관.
 *
 * 화면 px은 CSS px 기준. 캔버스는 devicePixelRatio 만큼 키워서 선명하게 그림.
 * 보이는 부분만 원본에서 잘라 그리므로 아주 큰 캔버스를 만들지 않는다.
 */
(function () {
  'use strict';

  const MAX_AREA = 16 * 1000 * 1000;   // 휴대폰(특히 아이폰) 캔버스 한계 안쪽

  function ZoomViewer(opts) {
    this.canvas = opts.canvas;
    this.mini = opts.minimap;
    this.settings = opts.settings;
    this.ctx = this.canvas.getContext('2d');
    this.mctx = this.mini.getContext('2d');
    this.cx = 0.5;            // 보고 있는 위치(그림 전체 기준 0~1)
    this.cy = 0.5;
    this.zoom = opts.settings.defaultZoom || 200;
    this._bind();
  }

  /**
   * file: PrintFile.load 결과, outW/outH: 제작 사이즈(cm)
   */
  ZoomViewer.prototype.setSource = function (file, outW, outH) {
    this.file = file;
    this.outW = outW;
    this.outH = outH;
    this.cx = 0.5;
    this.cy = 0.5;
    this.src = file.type === 'pdf'
      ? { el: file.img, w: file.img.width, h: file.img.height }   // 우선 미리보기로 그리고, 보이는 부분은 선명하게 다시 그림
      : this._prepareSource(file);
    this.draw();
  };

  /* 필요 이상으로 큰 원본은 화면 차이가 없는 크기까지만 줄여서 메모리를 아낀다 */
  ZoomViewer.prototype._prepareSource = function (file) {
    const S = this.settings;
    const maxZoom = Math.max.apply(null, S.zoomLevels) / 100;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    let needW = file.pxW, needH = file.pxH;
    if (S.mode !== 'photoshop') {
      needW = Math.ceil(this.outW / 2.54 * S.screenPpi * maxZoom * dpr);
      needH = Math.ceil(this.outH / 2.54 * S.screenPpi * maxZoom * dpr);
    }
    let tw = Math.min(file.pxW, needW), th = Math.min(file.pxH, needH);
    // 세로/가로를 따로 줄이면 늘어나는 정도가 달라지므로 각각 원본보다 작을 때만 줄임
    const area = tw * th;
    if (area > MAX_AREA) { const k = Math.sqrt(MAX_AREA / area); tw = Math.floor(tw * k); th = Math.floor(th * k); }
    if (tw >= file.pxW && th >= file.pxH) return { el: file.img, w: file.pxW, h: file.pxH };
    try {
      const c = document.createElement('canvas');
      c.width = tw; c.height = th;
      const x = c.getContext('2d');
      x.imageSmoothingEnabled = true;
      x.imageSmoothingQuality = 'high';
      x.drawImage(file.img, 0, 0, tw, th);
      return { el: c, w: tw, h: th };
    } catch (e) {
      return { el: file.img, w: file.pxW, h: file.pxH };
    }
  };

  ZoomViewer.prototype.setZoom = function (z) {
    this.zoom = z;
    this.draw();
  };

  /* 그림 전체가 화면에서 차지할 크기 (CSS px) */
  ZoomViewer.prototype._virtualSize = function () {
    const S = this.settings, k = this.zoom / 100;
    if (S.mode === 'photoshop') return { w: this.file.pxW * k, h: this.file.pxH * k };
    const pxPerCm = S.screenPpi / 2.54 * k;
    return { w: this.outW * pxPerCm, h: this.outH * pxPerCm };
  };

  ZoomViewer.prototype.draw = function () {
    if (!this.file) return;
    const c = this.canvas, ctx = this.ctx;
    const cssW = c.clientWidth, cssH = c.clientHeight;
    if (!cssW || !cssH) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    if (c.width !== Math.round(cssW * dpr) || c.height !== Math.round(cssH * dpr)) {
      c.width = Math.round(cssW * dpr);
      c.height = Math.round(cssH * dpr);
    }
    const v = this._virtualSize();
    this.vw = v.w; this.vh = v.h; this.viewW = cssW; this.viewH = cssH;
    this._clamp();

    // 보이는 영역 (가상 그림 좌표, CSS px)
    let x0 = this.cx * v.w - cssW / 2, y0 = this.cy * v.h - cssH / 2;
    let dx = 0, dy = 0, dw = cssW, dh = cssH;
    if (v.w <= cssW) { x0 = 0; dx = (cssW - v.w) / 2; dw = v.w; }
    if (v.h <= cssH) { y0 = 0; dy = (cssH - v.h) / 2; dh = v.h; }

    const src = this.src;
    const sx = x0 / v.w * src.w, sy = y0 / v.h * src.h;
    const sw = dw / v.w * src.w, sh = dh / v.h * src.h;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#d9dce1';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.imageSmoothingEnabled = this.settings.interpolation !== 'pixel';
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = '#fff';
    ctx.fillRect(dx * dpr, dy * dpr, dw * dpr, dh * dpr);
    ctx.drawImage(src.el, sx, sy, sw, sh, dx * dpr, dy * dpr, dw * dpr, dh * dpr);

    this._drawMini();
    if (this.file.type === 'pdf') this._schedulePdf({ x0: x0, y0: y0, dx: dx, dy: dy, dw: dw, dh: dh, vw: v.w, vh: v.h, dpr: dpr });
  };

  /*
   * PDF: 지금 보이는 부분만 실제 배율로 렌더링.
   * 글자·도형(벡터)은 항상 선명하고, PDF 안에 들어간 사진은 실제처럼 늘어나 보인다.
   */
  ZoomViewer.prototype._schedulePdf = function (r) {
    const self = this;
    clearTimeout(this._pdfTimer);
    if (this._pdfTask) { try { this._pdfTask.cancel(); } catch (e) {} this._pdfTask = null; }
    const token = (this._pdfToken = (this._pdfToken || 0) + 1);
    this._pdfTimer = setTimeout(function () { self._renderPdf(r, token); }, 120);
  };

  ZoomViewer.prototype._renderPdf = function (r, token) {
    const f = this.file, c = this.canvas, self = this;
    if (!f || f.type !== 'pdf') return;
    const off = this._off || (this._off = document.createElement('canvas'));
    off.width = c.width; off.height = c.height;
    const octx = off.getContext('2d');
    const vp = f.page.getViewport({ scale: 1 });
    const sx = r.vw / vp.width * r.dpr, sy = r.vh / vp.height * r.dpr;   // 비율이 달라도(늘린 경우) 그대로 반영
    const task = f.page.render({
      canvasContext: octx,
      viewport: vp,
      transform: [sx, 0, 0, sy, (r.dx - r.x0) * r.dpr, (r.dy - r.y0) * r.dpr],
      background: '#ffffff'
    });
    this._pdfTask = task;
    task.promise.then(function () {
      if (token !== self._pdfToken || f !== self.file) return;
      const x = Math.round(r.dx * r.dpr), y = Math.round(r.dy * r.dpr);
      const w = Math.round(r.dw * r.dpr), h = Math.round(r.dh * r.dpr);
      self.ctx.drawImage(off, x, y, w, h, x, y, w, h);
    }).catch(function () { /* 이동 중 취소됨 */ });
  };

  ZoomViewer.prototype._clamp = function () {
    const hx = this.viewW / 2 / this.vw, hy = this.viewH / 2 / this.vh;
    this.cx = hx >= 0.5 ? 0.5 : Math.min(1 - hx, Math.max(hx, this.cx));
    this.cy = hy >= 0.5 ? 0.5 : Math.min(1 - hy, Math.max(hy, this.cy));
  };

  /* 미니맵: 제작 사이즈 비율로 전체 그림 + 지금 보는 위치(네모) */
  ZoomViewer.prototype._drawMini = function () {
    const m = this.mini, ctx = this.mctx;
    const S = this.settings;
    const aspect = S.mode === 'photoshop' ? this.file.pxW / this.file.pxH : this.outW / this.outH;
    const box = 110;
    let w = box, h = box / aspect;
    if (h > box) { h = box; w = box * aspect; }
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    m.style.width = Math.round(w) + 'px';
    m.style.height = Math.round(h) + 'px';
    m.width = Math.round(w * dpr);
    m.height = Math.round(h * dpr);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(this.file.thumb, 0, 0, m.width, m.height);

    const rw = Math.min(1, this.viewW / this.vw), rh = Math.min(1, this.viewH / this.vh);
    const rx = (this.cx - rw / 2) * m.width, ry = (this.cy - rh / 2) * m.height;
    ctx.fillStyle = 'rgba(0,0,0,.35)';
    ctx.fillRect(0, 0, m.width, m.height);
    ctx.drawImage(this.file.thumb,
      (this.cx - rw / 2) * this.file.thumb.width, (this.cy - rh / 2) * this.file.thumb.height,
      rw * this.file.thumb.width, rh * this.file.thumb.height,
      rx, ry, rw * m.width, rh * m.height);
    ctx.strokeStyle = '#2f6bff';
    ctx.lineWidth = 2 * dpr;
    ctx.strokeRect(rx + dpr, ry + dpr, Math.max(2, rw * m.width - 2 * dpr), Math.max(2, rh * m.height - 2 * dpr));
  };

  ZoomViewer.prototype._bind = function () {
    const self = this, c = this.canvas, m = this.mini;
    let drag = null;

    c.addEventListener('pointerdown', function (e) {
      drag = { x: e.clientX, y: e.clientY, cx: self.cx, cy: self.cy };
      c.setPointerCapture(e.pointerId);
      c.classList.add('grabbing');
    });
    c.addEventListener('pointermove', function (e) {
      if (!drag || !self.file) return;
      self.cx = drag.cx - (e.clientX - drag.x) / self.vw;
      self.cy = drag.cy - (e.clientY - drag.y) / self.vh;
      self._schedule();
    });
    const end = function () { drag = null; c.classList.remove('grabbing'); };
    c.addEventListener('pointerup', end);
    c.addEventListener('pointercancel', end);

    // 미니맵을 누르거나 끌면 그 위치로 이동
    let mdrag = false;
    const jump = function (e) {
      const r = m.getBoundingClientRect();
      self.cx = (e.clientX - r.left) / r.width;
      self.cy = (e.clientY - r.top) / r.height;
      self._schedule();
    };
    m.addEventListener('pointerdown', function (e) { mdrag = true; m.setPointerCapture(e.pointerId); jump(e); });
    m.addEventListener('pointermove', function (e) { if (mdrag) jump(e); });
    m.addEventListener('pointerup', function () { mdrag = false; });
    m.addEventListener('pointercancel', function () { mdrag = false; });
  };

  ZoomViewer.prototype._schedule = function () {
    if (this._raf) return;
    const self = this;
    this._raf = requestAnimationFrame(function () { self._raf = 0; self.draw(); });
  };

  /* 화질 판정: 실제 출력 밀도 = 원본 px ÷ 제작 사이즈(인치), 가로·세로 중 낮은 값 */
  ZoomViewer.quality = function (file, outW, outH, item, settings) {
    if (file.type === 'pdf') return { level: 'pdf' };
    const density = Math.min(file.pxW / (outW / 2.54), file.pxH / (outH / 2.54));
    const q = settings.quality[item] || settings.quality.etc;
    return { density: density, level: density >= q.good ? 'good' : density >= q.ok ? 'ok' : 'low' };
  };

  window.ZoomViewer = ZoomViewer;
})();
