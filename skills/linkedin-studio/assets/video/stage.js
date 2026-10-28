// Deterministic playback for studio videos: video.py calls __setup() once, then __seek(ms) before every frame.
// Nothing here reads the clock; every visible thing is a function of the time passed in.
(() => {
  const scenes = [...document.querySelectorAll('.scene')];
  const span = (el) => [parseFloat(el.dataset.start), parseFloat(el.dataset.end)];

  // Largest font size at which a box's content fits (text grows on sparse scenes, shrinks on dense ones).
  function fit(box) {
    const over = () =>
      box.scrollHeight > box.clientHeight + 1 ||
      box.scrollWidth > box.clientWidth + 1 ||
      [...box.querySelectorAll('pre, .num, .lab')].some((p) => p.scrollWidth > p.clientWidth + 1);
    const max = parseFloat(box.dataset.max);
    let lo = Math.max(8, Math.floor(max * 0.2)), hi = max;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      box.style.fontSize = mid + 'px';
      if (over()) hi = mid - 1; else lo = mid;
    }
    box.style.fontSize = lo + 'px';
    return { px: lo, overflow: over() };
  }

  // A clip's window hugs the recording: the largest box with the recording's aspect ratio inside the free area.
  function sizeWindow(scene) {
    const box = scene.querySelector('.box'), win = scene.querySelector('.win');
    if (!box || !win) return;
    const bar = win.querySelector('.bar').offsetHeight;
    const ar = parseFloat(win.dataset.ar);
    let w = box.clientWidth, h = w / ar + bar;
    if (h > box.clientHeight) { h = box.clientHeight; w = (h - bar) * ar; }
    win.style.width = Math.floor(w) + 'px';
    win.style.height = Math.floor(h) + 'px';
  }

  window.__setup = async () => {
    await document.fonts.ready;
    // Measure without the entrance offsets: a transform still counts as overflow and would shrink every scene.
    const still = document.createElement('style');
    still.textContent = '*, *::before, *::after { animation: none !important; }';
    document.head.appendChild(still);
    const report = [];
    for (const s of scenes) {
      s.classList.add('on');
      const r = { id: s.id, fits: [] };
      // Clip captions are fitted first so the window gets whatever height is left.
      for (const f of s.querySelectorAll('.fit')) r.fits.push({ role: f.dataset.role, ...fit(f) });
      sizeWindow(s);
      s.classList.remove('on');
      report.push(r);
    }
    still.remove();
    return report;
  };

  const counters = [...document.querySelectorAll('[data-count]')];
  const easeOut = (x) => 1 - Math.pow(1 - x, 4);
  function formatCount(el, p) {
    const to = parseFloat(el.dataset.count), dec = parseInt(el.dataset.dec || '0', 10);
    let v = (to * easeOut(p)).toFixed(dec);
    if (el.dataset.sep) {
      const [i, f] = v.split('.');
      v = i.replace(/\B(?=(\d{3})+(?!\d))/g, el.dataset.sep) + (f ? '.' + f : '');
    }
    return (el.dataset.pre || '') + v + (el.dataset.suf || '');
  }

  const shots = [...document.querySelectorAll('img.shot')];
  let shown = '';

  // Returns false when this frame is identical to the previous one (no scene change, nothing in motion), so the
  // renderer can reuse the last capture instead of taking a new one.
  window.__seek = async (ms) => {
    const t = ms / 1000;
    let on = '';
    for (const s of scenes) {
      const [a, b] = span(s);
      const vis = t >= a - 0.05 && t < b + 0.05;
      s.classList.toggle('on', vis);
      if (vis) on += s.id + ',';
    }
    let moving = on !== shown;
    shown = on;
    // getAnimations() flushes style, so scenes switched on above are included.
    for (const a of document.getAnimations()) {
      a.pause();
      a.currentTime = ms;
      const k = a.effect.getTiming();
      const start = k.delay, end = k.delay + k.duration * (k.iterations || 1);
      if (ms >= start - 40 && ms <= end + 40) moving = true;
    }
    for (const el of counters) {
      const t0 = parseFloat(el.dataset.t), dur = parseFloat(el.dataset.dur);
      const p = (t - t0) / dur;
      if (p > -0.05 && p < 1.05 && el.closest('.scene').classList.contains('on')) moving = true;
      el.textContent = formatCount(el, Math.min(1, Math.max(0, p)));
    }
    const waits = [];
    for (const img of shots) {
      const s = img.closest('.scene');
      if (!s.classList.contains('on')) continue;
      const t0 = parseFloat(img.dataset.t0), n = parseInt(img.dataset.n, 10);
      const k = Math.min(n - 1, Math.max(0, Math.floor((t - t0) * 30 * parseFloat(img.dataset.speed))));
      const src = `${img.dataset.dir}/${String(k + 1).padStart(5, '0')}.jpg`;
      if (img.getAttribute('src') !== src) {
        img.setAttribute('src', src);
        waits.push(img.decode().catch(() => {}));
        moving = true;
      }
    }
    if (!moving) return false;
    await Promise.all(waits);
    await new Promise((r) => requestAnimationFrame(() => r()));
    return true;
  };
})();
