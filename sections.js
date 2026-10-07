// The layer list's sections (Objects, Lights, Cameras) as one stack, without a page: what the editor draws (engine.js buildUI) and what
// the unit tests check (tests/unit/js/sections.test.mjs). Owner 2026-10-06, three screenshots:
//  - «когда я двигаю за одну из этих, нижняя должна тоже с ней идти»: a handle moves the section above it; the sections below keep their
//    size and ride along; the room comes from the free space at the bottom, then from the last section, then from the ones above it, each
//    down to one row. Up is the mirror: the section above shrinks (then the ones above it), the last section below takes the room.
//  - «если я какое-то складываю, то у других появляется больше пространства»: a folded section's room goes to the open ones, its title
//    rides down with the stack (the last one sits at the panel's bottom when the rows above fill it); unfolded, it gets its size back.
//  - «странное расстояние, когда в сложенной позиции»: a handle takes no room (engine.js draws it over the line), and there is none
//    next to a folded section.
// A section never shows empty room inside: it is at most as tall as its rows, and room never stays empty at the bottom while a section is
// cut short. A section without a size (automatic) wants all its rows; when they do not fit, the biggest gives first, so a short section keeps
// its rows while a big one scrolls (owner 2026-10-07).
//
//   list: the shown sections in order, [{ k, content, min? }], content = the rows' height in px, min = how short it may get (default one row)
//   st:   { [k]: { size: px | null, shut, by?: the handle that sized it, was?: an automatic one's height when it was folded } }
//   H:    the stack's height in px (the titles and the rows)
//   o:    { head: a title's height (30), min: one row (28), open: a search shows every section without changing st }
const HEAD = 30, MIN = 28;
const conf = o => ({ head: (o && o.head) || HEAD, min: (o && o.min) || MIN, open: !!(o && o.open) });
const copy = st => Object.fromEntries(Object.entries(st || {}).map(([k, v]) => [k, { size: null, shut: false, ...v }]));
const total = (xs, f) => xs.reduce((n, x) => n + f(x), 0);
// how short a section may get: its own least (the rows that must stay in view: engine.js gives the active and the selected ones, 0 for none,
// owner 2026-10-07), or one row; never more than its rows
const least = (s, min) => Math.min(s.min != null ? s.min : min, s.content);

export function layout(list, st, H, o) {
  const { head, min, open } = conf(o);
  const isShut = s => !open && !!(st[s.k] && st[s.k].shut), sizeOf = s => (st[s.k] && st[s.k].size != null ? st[s.k].size : null);
  const avail = Math.max(0, Math.round(H) - list.length * head), mn = s => least(s, min);
  const h = {}, shut = {}, top = {}, handles = {};
  for (const s of list) { h[s.k] = 0; shut[s.k] = isShut(s); }
  // each open section wants its rows, or its size when a handle set one (never more than its rows)
  const opens = list.filter(s => !shut[s.k]);
  for (const s of opens) h[s.k] = sizeOf(s) != null ? Math.max(mn(s), Math.min(s.content, Math.round(sizeOf(s)))) : s.content;
  // too little room: the biggest gives first, down to the next biggest, then those two together, and so on to a row each; a short section
  // keeps its rows while a big one can scroll (owner 2026-10-07: Lights was cut to one row while all 18 cameras showed)
  let over = total(opens, s => h[s.k]) - avail;
  while (over > 0) {
    const cut = opens.filter(s => h[s.k] > mn(s)); if (!cut.length) break;
    const most = Math.max(...cut.map(s => h[s.k])), group = cut.filter(s => h[s.k] === most), lower = cut.filter(s => h[s.k] < most);
    const step = Math.max(1, Math.min(most - (lower.length ? Math.max(...lower.map(s => h[s.k])) : 0), Math.ceil(over / group.length)));
    for (const s of group) { const d = Math.min(step, h[s.k] - mn(s), over); h[s.k] -= d; over -= d; if (over <= 0) break; }
  }
  // room to spare never stays empty while a section is cut short (a size kept from an older drag): those get their rows back, from the top
  let spare = Math.max(0, -over);
  for (const s of opens) { const d = Math.min(spare, s.content - h[s.k]); if (d > 0) { h[s.k] += d; spare -= d; } }
  let y = 0;
  list.forEach((s, i) => { top[s.k] = y; y += head + h[s.k]; if (i && !shut[s.k] && !shut[list[i - 1].k]) handles[s.k] = list[i - 1].k; });
  return { h, top, shut, handles, free: Math.max(0, avail - total(list, s => h[s.k])), avail };
}

// a handle (named by the section below it) moved by dy from where the drag began (from: the layout then); returns the new st
export function drag(list, st, H, below, dy, from, o) {
  const { min } = conf(o), L = from || layout(list, st, H, o), above = L.handles[below];
  if (!above) return copy(st);
  const mn = s => least(s, min), i = list.findIndex(s => s.k === below), h = { ...L.h };
  const upper = list.slice(0, i).filter(s => !L.shut[s.k]).reverse(), lower = list.slice(i).filter(s => !L.shut[s.k]), a = upper[0];
  const step = Math.round(dy);
  if (step > 0) {
    // the section above grows up to its rows, out of the free room, then out of the sections below from the last one up
    const room = L.free + total(lower, s => Math.max(0, h[s.k] - mn(s)));
    const grow = Math.max(0, Math.min(step, a.content - h[a.k], room));
    h[a.k] += grow; let rem = grow - Math.min(grow, L.free);
    for (const s of [...lower].reverse()) { const d = Math.max(0, Math.min(rem, h[s.k] - mn(s))); h[s.k] -= d; rem -= d; }
  } else if (step < 0) {
    // the section above shrinks to a row, then the ones above it; the last section below takes the room up to its rows, then the one above
    // it: the stack never cuts a section to leave the room empty, so the handle stops when the ones below show all their rows
    let rem = Math.min(-step, total(lower, s => Math.max(0, s.content - h[s.k]))), got = 0;   // no more than the ones below can show
    for (const s of upper) { const d = Math.max(0, Math.min(rem, h[s.k] - mn(s))); h[s.k] -= d; rem -= d; got += d; }
    for (const s of [...lower].reverse()) { const d = Math.max(0, Math.min(got, s.content - h[s.k])); h[s.k] += d; got -= d; }
  }
  // the heights become sizes: what moved, and what is cut short (left automatic it would take the free room back). A section that shows all
  // its rows and did not move stays automatic, so a light added later still shows
  const out = copy(st);
  for (const s of list) {
    if (L.shut[s.k]) continue;
    // squeezed to its least, a section keeps size 0: it then follows what must stay in view (a row picked in it shows, none: its title alone)
    const c = out[s.k] = out[s.k] || { size: null, shut: false }, want = h[s.k] <= mn(s) ? 0 : h[s.k];
    if (h[s.k] !== L.h[s.k] || (c.size == null && h[s.k] < s.content)) { if (c.size !== want) c.by = below; c.size = want; }
    else if (c.size != null) c.size = want;
  }
  return out;
}

// a fold or an unfold of section k
export function fold(list, st, H, k, o) {
  const { min, open } = conf(o), out = copy(st), s = out[k] = out[k] || { size: null, shut: false }, sec = list.find(x => x.k === k);
  if (open || !sec) { s.shut = !s.shut; return out; }   // a search shows every section: only what is kept changes
  const mn = x => least(x, min), i = list.indexOf(sec);
  const near = st2 => [...list.slice(0, i).reverse(), ...list.slice(i + 1)].filter(x => !(st2[x.k] && st2[x.k].shut) && st2[x.k] && st2[x.k].size != null);
  if (!s.shut) {
    const L0 = layout(list, st, H, o);
    if (s.size == null) s.was = L0.h[k];
    s.shut = true;
    // the automatic sections take the room by themselves; a sized one with rows left to show takes the rest, the nearest above first
    const L1 = layout(list, out, H, o); let free = L1.free;
    for (const x of near(out)) { const d = Math.max(0, Math.min(free, x.content - L1.h[x.k])); if (d) { out[x.k].size = L1.h[x.k] + d; free -= d; } }
  } else {
    // unfolded: its size back, out of the free room, then out of the sized sections that took it, the nearest above first
    const L0 = layout(list, st, H, o), want = Math.min(sec.content, s.size != null ? s.size : s.was != null ? s.was : sec.content);
    let need = want - L0.free;
    for (const x of near(out)) { if (need <= 0) break; const d = Math.max(0, Math.min(need, L0.h[x.k] - mn(x))); if (d) { out[x.k].size = L0.h[x.k] - d; need -= d; } }
    s.shut = false; delete s.was;
  }
  return out;
}

// a double click on a handle: the section above it and the ones its drags sized are automatic again
export function reset(list, st, below) {
  const out = copy(st), i = list.findIndex(s => s.k === below), above = i > 0 ? list[i - 1].k : null;
  for (const [k, v] of Object.entries(out)) if (k === above || k === below || v.by === below) { v.size = null; delete v.by; }
  return out;
}
