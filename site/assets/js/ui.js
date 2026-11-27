// Shared UI: tooltip, counters, reveal-on-scroll, segmented controls, navigation.

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches || new URLSearchParams(location.search).has("static");
if (new URLSearchParams(location.search).has("static")) document.documentElement.classList.add("static");

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

// ---------------------------------------------------------------- tooltip
const tipEl = () => document.getElementById("tip");
export function showTip(html, x, y) {
  const t = tipEl();
  t.innerHTML = html;
  t.classList.add("show");
  const r = t.getBoundingClientRect();
  let left = x + 14, top = y + 14;
  if (left + r.width > innerWidth - 8) left = x - r.width - 14;
  if (top + r.height > innerHeight - 8) top = y - r.height - 14;
  t.style.left = Math.max(8, left) + "px";
  t.style.top = Math.max(8, top) + "px";
}
export function hideTip() { tipEl().classList.remove("show"); }
export function tipRows(title, rows, note, dot) {
  return `<div class="t">${dot ? `<i class="dot ${dot}"></i>` : ""}${esc(title)}</div>` +
    rows.map(([k, v]) => `<div class="r"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("") +
    (note ? `<div class="note">${esc(note)}</div>` : "");
}

// ---------------------------------------------------------------- counters & reveal
export function countUp(el, target, { decimals = 0, duration = 1400 } = {}) {
  const fmtv = v => v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  if (reduceMotion) { el.textContent = fmtv(target); return; }
  const t0 = performance.now();
  const step = now => {
    const p = Math.min(1, (now - t0) / duration);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmtv(target * e);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export function onVisible(el, fn, { threshold = 0.25, once = true } = {}) {
  if (reduceMotion) { fn(el); return null; }
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { fn(e.target); if (once) io.unobserve(e.target); }
  }, { threshold });
  io.observe(el);
  return io;
}

export function initReveal() {
  for (const el of $$(".reveal")) onVisible(el, x => x.classList.add("in"), { threshold: 0.08 });
}

// ---------------------------------------------------------------- segmented control
export function seg(container, onChange, attr) {
  const btns = $$("button", container);
  btns.forEach(b => b.addEventListener("click", () => {
    btns.forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    onChange(b.dataset[attr], b);
  }));
  return () => btns.find(b => b.getAttribute("aria-pressed") === "true")?.dataset[attr];
}

// ---------------------------------------------------------------- navigation
export function initNav() {
  const nav = $("#nav"), toggle = $("#nav-toggle"), bar = $("#nav-progress");
  const links = $$("#nav-links a");
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  links.forEach(a => a.addEventListener("click", () => { nav.classList.remove("open"); toggle.setAttribute("aria-expanded", "false"); }));
  const onScroll = () => {
    nav.classList.toggle("scrolled", scrollY > 10);
    const max = document.documentElement.scrollHeight - innerHeight;
    bar.style.width = (100 * scrollY / Math.max(1, max)) + "%";
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  const sections = links.map(a => document.querySelector(a.getAttribute("href")));
  const io = new IntersectionObserver(() => {
    const y = scrollY + innerHeight * 0.35;
    let cur = null;
    for (const s of sections) if (s && s.offsetTop <= y) cur = s.id;
    links.forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + cur));
  }, { threshold: [0, 0.2, 0.5] });
  sections.forEach(s => s && io.observe(s));
}
