/*
 * 브로애드 화질·사이즈 확인 페이지 — 설정 파일
 * ------------------------------------------------------------
 * 메모장으로 열어서 따옴표("") 안의 글자나 숫자만 바꾸세요.
 * 쉼표(,)와 중괄호({ })는 지우지 마세요.
 */
window.SETTINGS = {
  "companyName": "브로애드",
  "kakaoChannelUrl": "",
  "upscaleEmail": "BRO_AD@NAVER.COM",
  "upscaleOfferFor": ["good", "ok", "low", "pdf"],
  "defaultZoom": 200,
  "zoomLevels": [100, 200, 300],
  "mode": "illustrator",
  "interpolation": "smooth",
  "screenPpi": 72,
  "ratioTolerancePercent": 1,
  "maxFileSizeMB": 200,
  "noSizeInfoDpiAtOrBelow": 72,
  "showQualityBadge": true,
  "quality": {
    "standee": { "good": 100, "ok": 60 },
    "print":   { "good": 100, "ok": 60 },
    "poster":  { "good": 100, "ok": 60 },
    "banner":  { "good": 50,  "ok": 30 },
    "etc":     { "good": 80,  "ok": 50 }
  },
  "brandColor": "#2F6BFF"
};
