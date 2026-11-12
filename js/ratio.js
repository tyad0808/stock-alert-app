/*
 * 비율 계산
 *   원본비율 = 원본가로 ÷ 원본세로
 *   요청비율 = 요청가로 ÷ 요청세로
 *   차이(%) = |요청비율 ÷ 원본비율 − 1| × 100
 */
(function () {
  'use strict';

  function judge(origW, origH, reqW, reqH, tolerancePercent) {
    const o = origW / origH;
    const r = reqW / reqH;
    const k = r / o;                       // 1보다 크면 옆으로 늘어남, 작으면 홀쭉해짐
    const diff = Math.abs(k - 1) * 100;
    return {
      ok: diff <= tolerancePercent,
      diffPercent: diff,
      wider: k > 1,
      // 비율대로 맞추기 제안값 (두 가지 모두)
      fitByHeight: { w: reqH * o, h: reqH },
      fitByWidth: { w: reqW, h: reqW / o }
    };
  }

  /* "가로 2 : 세로 5" 처럼 간단한 정수 비율로 표시 (1% 안쪽으로 맞으면) */
  function simpleRatio(w, h) {
    const r = w / h;
    for (let b = 1; b <= 20; b++) {
      const a = r * b;
      const ra = Math.round(a);
      if (ra >= 1 && ra <= 40 && Math.abs(a - ra) / a < 0.01) return { w: String(ra), h: String(b) };
    }
    // 간단한 정수로 안 떨어지면 짧은 쪽을 1로
    if (w <= h) return { w: '1', h: fmt(h / w, 2) };
    return { w: fmt(w / h, 2), h: '1' };
  }

  /* 숫자 표시: 소수점 digits자리까지, 불필요한 0은 지움 */
  function fmt(n, digits) {
    const d = digits == null ? 1 : digits;
    const s = (Math.round(n * Math.pow(10, d)) / Math.pow(10, d)).toFixed(d);
    return s.indexOf('.') >= 0 ? s.replace(/\.?0+$/, '') : s;
  }

  window.Ratio = { judge: judge, simpleRatio: simpleRatio, fmt: fmt };
})();
