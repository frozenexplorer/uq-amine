// Hero background: CO2 molecules (O=C=O) drift through a loose network of amine sites.
// A free site captures a passing CO2, holds it for a while, then releases it: the absorb /
// regenerate cycle, kept faint so it never competes with the text.
import { reduceMotion } from "../ui.js";

export function initHero() {
  const canvas = document.getElementById("hero-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, dpr = 1, nodes = [], mols = [], running = false, raf = 0;

  const rand = (a, b) => a + Math.random() * (b - a);
  const fade = x => 0.25 + 0.75 * Math.min(1, Math.max(0, (x / W - 0.15) / 0.55)); // fainter behind the text

  function setup() {
    dpr = Math.min(2, devicePixelRatio || 1);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const area = W * H;
    const nN = Math.round(Math.min(70, Math.max(18, area / 24000)));
    nodes = Array.from({ length: nN }, () => ({
      x: W * (0.2 + 0.8 * Math.pow(Math.random(), 0.75)), y: rand(0, H),
      vx: rand(-0.06, 0.06), vy: rand(-0.06, 0.06), busy: null, cool: 0,
    }));
    mols = Array.from({ length: Math.round(nN * 1.2) }, () => ({
      x: rand(0, W), y: rand(0, H), vx: rand(-0.32, 0.32), vy: rand(-0.22, 0.22),
      a: rand(0, Math.PI), va: rand(-0.01, 0.01), bound: null, t: 0, glow: 0,
    }));
  }

  function step() {
    for (const n of nodes) {
      n.x += n.vx; n.y += n.vy;
      if (n.x < W * 0.12 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
      if (n.cool > 0) n.cool--;
    }
    for (const m of mols) {
      if (m.bound) {
        const n = m.bound;
        const tx = n.x + Math.cos(m.slot) * 11, ty = n.y + Math.sin(m.slot) * 11;
        m.x += (tx - m.x) * 0.08; m.y += (ty - m.y) * 0.08;
        m.a += (m.slot - m.a) * 0.05;
        m.glow = Math.min(1, m.glow + 0.04);
        if (--m.t <= 0) {
          n.busy = null; n.cool = 160; m.bound = null;
          m.vx = Math.cos(m.slot) * 0.45; m.vy = Math.sin(m.slot) * 0.45;
        }
        continue;
      }
      m.glow = Math.max(0, m.glow - 0.02);
      m.x += m.vx; m.y += m.vy; m.a += m.va;
      if (m.x < -10) m.x = W + 10; else if (m.x > W + 10) m.x = -10;
      if (m.y < -10) m.y = H + 10; else if (m.y > H + 10) m.y = -10;
      for (const n of nodes) {
        if (n.busy || n.cool) continue;
        const dx = n.x - m.x, dy = n.y - m.y;
        if (dx * dx + dy * dy < 22 * 22) {
          n.busy = m; m.bound = n; m.slot = Math.atan2(-dy, -dx); m.t = rand(220, 520);
          break;
        }
      }
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    const L = 130;
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 > L * L) continue;
        const k = (1 - Math.sqrt(d2) / L) * 0.12 * fade((a.x + b.x) / 2);
        ctx.strokeStyle = `rgba(92,200,224,${k})`;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
    for (const n of nodes) {
      const f = fade(n.x);
      if (n.busy) {
        ctx.strokeStyle = `rgba(92,200,224,${0.55 * f * n.busy.glow})`;
        ctx.beginPath(); ctx.moveTo(n.x, n.y); ctx.lineTo(n.busy.x, n.busy.y); ctx.stroke();
        ctx.fillStyle = `rgba(92,200,224,${0.12 * f})`;
        ctx.beginPath(); ctx.arc(n.x, n.y, 9, 0, 6.283); ctx.fill();
      }
      ctx.fillStyle = `rgba(92,200,224,${0.7 * f})`;
      ctx.beginPath(); ctx.arc(n.x, n.y, 2.4, 0, 6.283); ctx.fill();
    }
    for (const m of mols) {
      const f = fade(m.x) * (0.75 + 0.25 * m.glow);
      const cx = Math.cos(m.a) * 5.2, cy = Math.sin(m.a) * 5.2;
      ctx.strokeStyle = `rgba(201,211,224,${0.28 * f})`;
      ctx.beginPath(); ctx.moveTo(m.x - cx, m.y - cy); ctx.lineTo(m.x + cx, m.y + cy); ctx.stroke();
      ctx.fillStyle = `rgba(201,211,224,${0.6 * f})`;
      ctx.beginPath(); ctx.arc(m.x - cx, m.y - cy, 2.1, 0, 6.283); ctx.arc(m.x + cx, m.y + cy, 2.1, 0, 6.283); ctx.fill();
      ctx.fillStyle = `rgba(226,166,59,${0.75 * f})`;
      ctx.beginPath(); ctx.arc(m.x, m.y, 1.8, 0, 6.283); ctx.fill();
    }
  }

  function loop() {
    if (!running) return;
    step(); draw();
    raf = requestAnimationFrame(loop);
  }
  const start = () => { if (!running && !reduceMotion) { running = true; loop(); } };
  const stop = () => { running = false; cancelAnimationFrame(raf); };

  setup();
  if (reduceMotion) { for (let i = 0; i < 400; i++) step(); draw(); }
  new ResizeObserver(() => { setup(); if (!running) draw(); }).observe(canvas);
  new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop())).observe(canvas);
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
}
