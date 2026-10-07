// Hyimg 3D, the turntable of a 3D file as the pages ask for it (owner 2026-10-06): the numbers of its sheet and the urls of Hyimg's server
// (/api/sprite). Small and free of three.js: the card's recent list and the library need only these; sprites.js draws the sheets.
export const SHEET = { n: 36, cols: 6, cell: 256 };   // 36 views, 10° apart, in 6 columns: a sheet of 1536 × 1536 px
export const sheetUrl = (it, v) => `/api/sprite?p=${encodeURIComponent(it.path)}&v=${v || (it.sprite && it.sprite.v) || it.ver || 0}`;
export const stillUrl = (it, s = 240) => `${sheetUrl(it)}&s=${s}`;   // the first view, as a picture of its own
// the data-spin of a tile (review/ui/spin.js)
export const spinOf = it => it.sprite ? JSON.stringify({ sheet: sheetUrl(it), n: it.sprite.n, cols: it.sprite.cols }) : "";
