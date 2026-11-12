/*
 * 파일 읽기 + 원본 사이즈 인식
 * - 파일은 서버로 보내지 않고 브라우저 안에서만 읽는다.
 * - JPG: Photoshop 해상도 정보(8BIM) > EXIF > JFIF 순서로 DPI를 찾는다.
 * - PNG: pHYs 청크(미터당 픽셀)를 읽는다.
 */
(function () {
  'use strict';

  function ascii(dv, off, len) {
    let s = '';
    for (let i = 0; i < len && off + i < dv.byteLength; i++) s += String.fromCharCode(dv.getUint8(off + i));
    return s;
  }

  /* 파일 앞부분의 바이트로 실제 형식을 판별 (확장자는 믿지 않음) */
  function sniffType(dv) {
    if (dv.byteLength >= 3 && dv.getUint8(0) === 0xFF && dv.getUint8(1) === 0xD8 && dv.getUint8(2) === 0xFF) return 'jpg';
    if (dv.byteLength >= 8 && dv.getUint32(0) === 0x89504E47 && dv.getUint32(4) === 0x0D0A1A0A) return 'png';
    // PDF 또는 'PDF 호환'으로 저장된 AI 파일 (앞 1KB 안에 %PDF- 가 있음)
    const head = ascii(dv, 0, Math.min(1024, dv.byteLength));
    if (head.indexOf('%PDF-') !== -1) return 'pdf';
    if (head.indexOf('%!PS-Adobe') !== -1) return 'ai-old';
    if (head.slice(0, 4) === '8BPS') return 'psd';
    if (head.slice(4, 12) === 'ftypheic' || head.slice(4, 12) === 'ftypheix' || head.slice(4, 12) === 'ftypmif1') return 'heic';
    return 'unknown';
  }

  /* ---------- EXIF (TIFF 구조) ---------- */
  function readExif(dv, base, end) {
    if (base + 8 > end) return null;
    const order = ascii(dv, base, 2);
    const le = order === 'II';
    if (!le && order !== 'MM') return null;
    const u16 = (o) => dv.getUint16(o, le);
    const u32 = (o) => dv.getUint32(o, le);
    if (u16(base + 2) !== 42) return null;
    const ifd = base + u32(base + 4);
    if (ifd + 2 > end) return null;
    const n = u16(ifd);
    const out = {};
    for (let i = 0; i < n; i++) {
      const e = ifd + 2 + i * 12;
      if (e + 12 > end) break;
      const tag = u16(e);
      const type = u16(e + 2);
      if (tag === 0x011A || tag === 0x011B) {           // XResolution / YResolution (RATIONAL)
        const vo = base + u32(e + 8);
        if (type === 5 && vo + 8 <= end) {
          const den = u32(vo + 4);
          if (den) out[tag === 0x011A ? 'x' : 'y'] = u32(vo) / den;
        }
      } else if (tag === 0x0128) {                      // ResolutionUnit: 2=inch, 3=cm
        out.unit = u16(e + 8);
      } else if (tag === 0x0112) {                      // Orientation
        out.orientation = u16(e + 8);
      }
    }
    if (out.x && out.unit === 3) { out.x *= 2.54; if (out.y) out.y *= 2.54; }
    if (out.x && out.unit === 1) { delete out.x; delete out.y; }   // 단위 없음 = 비율 정보일 뿐
    return out;
  }

  /* ---------- Photoshop 해상도 정보 (APP13 / 8BIM 0x03ED) ---------- */
  function readPhotoshopRes(dv, start, end) {
    let p = start;
    while (p + 12 <= end) {
      if (ascii(dv, p, 4) !== '8BIM') return null;
      const id = dv.getUint16(p + 4);
      let q = p + 6;
      const nameLen = dv.getUint8(q);
      q += 1 + nameLen;
      if ((1 + nameLen) % 2) q++;
      if (q + 4 > end) return null;
      const size = dv.getUint32(q);
      q += 4;
      if (id === 0x03ED && size >= 16 && q + 16 <= end) {
        const x = dv.getUint32(q) / 65536;     // 항상 '인치당 픽셀'로 저장됨
        const y = dv.getUint32(q + 8) / 65536;
        return x > 0 ? { x: x, y: y || x } : null;
      }
      p = q + size + (size % 2);
    }
    return null;
  }

  function readJpegInfo(dv) {
    let off = 2;
    let jfif = null, exif = null, ps = null;
    while (off + 4 <= dv.byteLength) {
      if (dv.getUint8(off) !== 0xFF) break;
      const m = dv.getUint8(off + 1);
      if (m === 0xFF) { off++; continue; }
      if (m === 0xD8 || m === 0x01 || (m >= 0xD0 && m <= 0xD7)) { off += 2; continue; }
      if (m === 0xDA || m === 0xD9) break;               // 이미지 데이터 시작 → 끝
      const len = dv.getUint16(off + 2);
      const s = off + 4, end = Math.min(off + 2 + len, dv.byteLength);
      if (m === 0xE0 && ascii(dv, s, 5) === 'JFIF\0' && s + 12 <= end) {
        const unit = dv.getUint8(s + 7), x = dv.getUint16(s + 8), y = dv.getUint16(s + 10);
        if (unit === 1 && x) jfif = { x: x, y: y || x };
        else if (unit === 2 && x) jfif = { x: x * 2.54, y: (y || x) * 2.54 };
      } else if (m === 0xE1 && ascii(dv, s, 6) === 'Exif\0\0') {
        exif = readExif(dv, s + 6, end);
      } else if (m === 0xED && ascii(dv, s, 14) === 'Photoshop 3.0\0') {
        ps = readPhotoshopRes(dv, s + 14, end) || ps;
      } else if ((m >= 0xC0 && m <= 0xC3) && s + 6 <= end) {
        // 프레임 헤더: 성분 수 4 = CMYK
        const comps = dv.getUint8(s + 5);
        if (comps === 4) jfif = Object.assign(jfif || {}, { cmyk: true });
      }
      off += 2 + len;
    }
    let dpi = null;
    if (ps) dpi = ps;
    else if (exif && exif.x) dpi = { x: exif.x, y: exif.y || exif.x };
    else if (jfif && jfif.x) dpi = { x: jfif.x, y: jfif.y };
    return {
      dpi: dpi,
      orientation: (exif && exif.orientation) || 1,
      cmyk: !!(jfif && jfif.cmyk)
    };
  }

  function readPngInfo(dv) {
    let off = 8;
    while (off + 12 <= dv.byteLength) {
      const len = dv.getUint32(off);
      const type = ascii(dv, off + 4, 4);
      if (type === 'pHYs' && len >= 9) {
        const x = dv.getUint32(off + 8), y = dv.getUint32(off + 12), unit = dv.getUint8(off + 16);
        if (unit === 1 && x) return { dpi: { x: x * 0.0254, y: (y || x) * 0.0254 }, orientation: 1 };
        return { dpi: null, orientation: 1 };
      }
      if (type === 'IDAT' || type === 'IEND') break;
      off += 12 + len;
    }
    return { dpi: null, orientation: 1 };
  }

  function decodeImage(file) {
    return new Promise(function (resolve, reject) {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.decoding = 'async';
      img.onload = function () { resolve({ img: img, url: url }); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('decode')); };
      img.src = url;
    });
  }

  /* 화면 표시용으로 작게 줄인 그림 (원본 비율 유지) */
  function makeThumb(img, maxSide) {
    const w = img.naturalWidth, h = img.naturalHeight;
    const s = Math.min(1, maxSide / Math.max(w, h));
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(w * s));
    c.height = Math.max(1, Math.round(h * s));
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  /**
   * 파일을 읽어 결과를 돌려준다.
   * 실패 시 Error.code: 'tooLarge' | 'unsupported' | 'pdf' | 'broken'
   */
  async function load(file, settings) {
    const fail = (code) => { const e = new Error(code); e.code = code; return e; };
    if (file.size > settings.maxFileSizeMB * 1024 * 1024) throw fail('tooLarge');

    // 형식·DPI 정보는 앞부분에 있으므로 최대 1MB만 먼저 읽는다
    const headBuf = await file.slice(0, Math.min(file.size, 1024 * 1024)).arrayBuffer();
    const dv = new DataView(headBuf);
    const type = sniffType(dv);

    if (type === 'pdf') return loadPdf(file, fail);
    if (type === 'ai-old') throw fail('aiOld');
    if (type !== 'jpg' && type !== 'png') throw fail('unsupported');

    const meta = type === 'jpg' ? readJpegInfo(dv) : readPngInfo(dv);

    let decoded;
    try { decoded = await decodeImage(file); }
    catch (e) { throw fail('broken'); }
    const img = decoded.img;
    const pxW = img.naturalWidth, pxH = img.naturalHeight;
    if (!pxW || !pxH) throw fail('broken');

    // 휴대폰 사진처럼 회전 정보가 있으면 브라우저가 자동으로 돌려서 보여주므로 DPI 가로/세로도 바꿔준다
    let dpiX = meta.dpi && meta.dpi.x, dpiY = meta.dpi && meta.dpi.y;
    if (meta.orientation >= 5 && meta.orientation <= 8 && dpiX) { const t = dpiX; dpiX = dpiY; dpiY = t; }

    const limit = settings.noSizeInfoDpiAtOrBelow;
    const hasSize = !!(dpiX && dpiY && dpiX > limit + 0.5 && dpiY > limit + 0.5);

    return {
      name: file.name,
      type: type,
      img: img,
      objectUrl: decoded.url,
      thumb: makeThumb(img, 1600),
      pxW: pxW,
      pxH: pxH,
      dpiX: dpiX || null,
      dpiY: dpiY || null,
      hasSize: hasSize,
      // 실제 cm (크기 정보가 없으면 null)
      cmW: hasSize ? pxW / dpiX * 2.54 : null,
      cmH: hasSize ? pxH / dpiY * 2.54 : null,
      // 비율 계산용: 크기 정보가 있으면 cm 기준, 없으면 픽셀 기준
      ratioW: hasSize ? pxW / dpiX : pxW,
      ratioH: hasSize ? pxH / dpiY : pxH,
      cmyk: !!meta.cmyk
    };
  }

  /* ---------- PDF (+ 'PDF 호환'으로 저장된 AI) ---------- */
  function pdfLib() {
    const lib = window.pdfjsLib;
    if (lib && !lib.GlobalWorkerOptions.workerSrc) lib.GlobalWorkerOptions.workerSrc = 'lib/pdf.worker.min.js';
    return lib;
  }

  async function loadPdf(file, fail) {
    const lib = pdfLib();
    if (!lib) throw fail('broken');
    let pdf;
    try {
      const data = new Uint8Array(await file.arrayBuffer());
      pdf = await lib.getDocument({ data: data, isEvalSupported: false }).promise;
    } catch (e) {
      throw fail(e && e.name === 'PasswordException' ? 'password' : 'broken');
    }
    const info = await loadPdfPage(pdf, 1, file.name);
    return info;
  }

  /* PDF의 n번째 쪽을 읽어서 사이즈 + 미리보기 그림을 만든다 */
  async function loadPdfPage(pdf, n, name) {
    const page = await pdf.getPage(n);
    const vp1 = page.getViewport({ scale: 1 });             // 회전값 반영됨, pt 단위
    const unit = page.userUnit || 1;                         // 일러 '큰 대지'는 UserUnit으로 저장됨
    const wPt = vp1.width * unit, hPt = vp1.height * unit;

    // 미리보기용 그림 (긴 쪽 최대 3000px, 넓이 8백만px 이하)
    let scale = 3000 / Math.max(vp1.width, vp1.height);
    if (vp1.width * vp1.height * scale * scale > 8e6) scale = Math.sqrt(8e6 / (vp1.width * vp1.height));
    const vp = page.getViewport({ scale: scale });
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.floor(vp.width));
    c.height = Math.max(1, Math.floor(vp.height));
    await page.render({ canvasContext: c.getContext('2d'), viewport: vp, background: '#ffffff' }).promise;

    return {
      name: name,
      type: 'pdf',
      pdf: pdf,
      page: page,
      pageNum: n,
      pageCount: pdf.numPages,
      img: c,
      thumb: makeThumbFromCanvas(c, 1600),
      // 포토샵 방식에서 쓰는 기준 픽셀 (72dpi로 열었을 때와 같음)
      pxW: Math.round(wPt),
      pxH: Math.round(hPt),
      hasSize: true,
      cmW: wPt / 72 * 2.54,
      cmH: hPt / 72 * 2.54,
      ratioW: wPt,
      ratioH: hPt,
      pageW1: vp1.width,     // 확대 렌더링용 (scale 1 기준 크기)
      pageH1: vp1.height
    };
  }

  function makeThumbFromCanvas(src, maxSide) {
    const s = Math.min(1, maxSide / Math.max(src.width, src.height));
    if (s >= 1) return src;
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(src.width * s));
    c.height = Math.max(1, Math.round(src.height * s));
    const ctx = c.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(src, 0, 0, c.width, c.height);
    return c;
  }

  window.PrintFile = { load: load, loadPdfPage: loadPdfPage, _sniffType: sniffType, _readJpegInfo: readJpegInfo, _readPngInfo: readPngInfo };
})();
