"use strict";
// Rosto do Biony: olhos desenhados por funções de distância (SDF), animados com molas e
// mostrados numa grade de "pixels" grandes. Cada pixel acende na proporção em que o olho o
// cobre, então o movimento continua suave mesmo na grade.
//
// Independente do resto do app. Uso:
//   const face = BionyFace.create(canvas);
//   face.setState("ocioso" | "ouvindo" | "pensando" | "falando" | "sonolento" | "dormindo");
//   face.react("feliz" | "triste" | "duvida" | "confuso" | "surpreso" | "bravo" | "neutro", ms);
//   face.setLevel(0..1);   // volume da fala, enquanto "falando"
//   face.poke();           // reação a um toque
//
// As mesmas regras (expressões, molas, SDF) servem de referência para a tela do ESP32.

(function () {
  const COLOR = [79, 209, 232];
  const EYE_X = 0.62; // distância de cada olho ao centro, em "unidades" (1 unidade = meia altura da grade)

  // ------------------------------------------------------------------ expressões

  const BASE = { w: 0.62, h: 0.95, r: 0.24, lid: 0, slant: 0, happy: 0, dx: 0, dy: 0 };

  // Cada expressão: diferenças para o olho esquerdo (L), direito (R), ambos (both) e olhar.
  const EXPRESSIONS = {
    ocioso: {}, // estado de descanso
    neutro: {}, // reação "nenhuma"
    ouvindo: { both: { w: 0.68, h: 1.02, r: 0.28 }, look: [0, -0.05] },
    pensando: { both: { lid: 0.22, slant: -0.1 }, R: { h: 0.9 }, look: [0.34, -0.3] },
    falando: {},
    feliz: { both: { happy: 1, h: 0.78, w: 0.68 }, look: [0, -0.12] },
    triste: { both: { lid: 0.2, slant: -0.5, h: 0.9 }, look: [0, 0.2] },
    duvida: { L: { lid: 0.3, slant: 0.3 }, look: [0.1, -0.06] },
    confuso: { L: { h: 0.62, lid: 0.16, slant: 0.32, dy: 0.06 }, R: { w: 0.68, h: 1.02, r: 0.3, dy: -0.06 }, look: [-0.12, 0] },
    surpreso: { both: { w: 0.7, h: 1.08, r: 0.34 }, look: [0, -0.05] },
    bravo: { both: { lid: 0.28, slant: 0.72, h: 0.9 }, look: [0, 0.04] },
    sonolento: { both: { lid: 0.56, slant: -0.06 }, look: [0, 0.12] },
    dormindo: { both: { lid: 0.95, h: 0.9 }, look: [0, 0.2] },
  };

  const KEYS = Object.keys(BASE);

  function target(name) {
    const e = EXPRESSIONS[name] || {};
    const out = { lookX: (e.look || [0, 0])[0], lookY: (e.look || [0, 0])[1] };
    for (const side of ["L", "R"]) {
      const eye = { ...BASE, ...(e.both || {}), ...(e[side] || {}) };
      for (const key of KEYS) out[side + key] = eye[key];
    }
    return out;
  }

  // ------------------------------------------------------------------ geometria (SDF)

  function roundedBox(px, py, hw, hh, r) {
    r = Math.min(r, hw, hh);
    const qx = Math.abs(px) - (hw - r);
    const qy = Math.abs(py) - (hh - r);
    const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0));
    return outside + Math.min(Math.max(qx, qy), 0) - r;
  }

  // Distância (em unidades) de um ponto até a borda do olho; negativa = dentro.
  function eyeDistance(px, py, eye, inner) {
    const hw = eye.w / 2;
    const hh = eye.h / 2;
    let d = roundedBox(px, py, hw, hh, eye.r);
    // Pálpebra de cima: uma reta que pode inclinar (bravo/triste). `inner` = lado do nariz.
    const lineY = -hh + eye.lid * eye.h + eye.slant * px * inner;
    d = Math.max(d, (lineY - py) / Math.hypot(1, eye.slant));
    // Feliz: um círculo "come" a parte de baixo e o olho vira um arco (^ ^).
    if (eye.happy > 0.001) {
      const radius = eye.w * 0.72;
      const cy = hh - eye.happy * 0.78 * eye.h + radius;
      d = Math.max(d, radius - Math.hypot(px, py - cy));
    }
    return d;
  }

  // ------------------------------------------------------------------ pixel-fonts

  const GLYPHS = {
    z4: ["####", "..#.", ".#..", "####"],
    z5: ["#####", "...#.", "..#..", ".#...", "#####"],
    "?": [".###.", "#...#", "...#.", "..#..", "..#..", ".....", "..#.."],
  };

  // ------------------------------------------------------------------ rosto

  function create(canvas, options = {}) {
    const ctx = canvas.getContext("2d");
    const lit = document.createElement("canvas");
    const litCtx = lit.getContext("2d");
    const grid = document.createElement("canvas");
    const reduced = options.reducedMotion ?? matchMedia("(prefers-reduced-motion: reduce)").matches;
    const glow = "filter" in ctx;

    let state = "ocioso";
    let reaction = null; // { name, until }
    let level = 0;
    let levelSmooth = 0;
    const now = () => performance.now() / 1000;

    const value = target("neutro");
    const velocity = Object.fromEntries(Object.keys(value).map((k) => [k, 0]));
    let look = [0, 0];
    let nextSaccade = 0;
    let nextBlink = now() + 2;
    let blinkStart = -1;
    let blinkSlow = false;
    let doubleBlink = false;
    let zzz = [];
    let nextZ = 0;
    let layout = null;
    let raf = 0;
    let last = now();

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (layout && layout.width === width && layout.height === height) return;
      canvas.width = lit.width = grid.width = width;
      canvas.height = lit.height = grid.height = height;
      // Telas maiores ganham mais linhas: o rosto fica com a mesma proporção, só mais nítido.
      const rows = Math.max(22, Math.min(40, Math.round(canvas.clientHeight / 9)));
      const cell = Math.max(2, Math.floor(height / rows));
      const cols = Math.floor(width / cell);
      layout = {
        width, height, rows, cols, cell,
        x0: Math.floor((width - cols * cell) / 2),
        y0: Math.floor((height - rows * cell) / 2),
        unit: rows / 2, // células por unidade
      };
      // Pixels apagados (a "tela LCD"), desenhados uma vez só.
      const g = grid.getContext("2d");
      g.clearRect(0, 0, width, height);
      g.fillStyle = `rgba(${COLOR}, 0.055)`;
      const size = cell * 0.82;
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          g.fillRect(layout.x0 + x * cell + (cell - size) / 2, layout.y0 + y * cell + (cell - size) / 2, size, size);
        }
      }
    }

    function currentExpression() {
      if (reaction && (reaction.until === Infinity || reaction.until > now())) return reaction.name;
      reaction = null;
      return state;
    }

    function blinkAmount(t) {
      if (state === "dormindo") return 0;
      if (blinkStart < 0 && t >= nextBlink) {
        blinkStart = t;
        blinkSlow = state === "sonolento";
      }
      if (blinkStart < 0) return 0;
      const close = blinkSlow ? 0.22 : 0.07;
      const hold = blinkSlow ? 0.25 : 0.03;
      const open = blinkSlow ? 0.4 : 0.12;
      const e = t - blinkStart;
      let amount;
      if (e < close) amount = e / close;
      else if (e < close + hold) amount = 1;
      else if (e < close + hold + open) amount = 1 - (e - close - hold) / open;
      else {
        blinkStart = -1;
        if (!doubleBlink && Math.random() < 0.18) {
          doubleBlink = true;
          nextBlink = t + 0.08;
        } else {
          doubleBlink = false;
          nextBlink = t + (state === "sonolento" ? 3 + Math.random() * 3 : 2.2 + Math.random() * 3.6);
        }
        return 0;
      }
      return Math.sin((amount * Math.PI) / 2);
    }

    function updateLook(t) {
      if (reduced) { look = [0, 0]; return; }
      if (t < nextSaccade) return;
      const range = { ocioso: [0.24, 0.13], ouvindo: [0.06, 0.04], pensando: [0.1, 0.06], falando: [0.08, 0.05] }[state];
      if (!range) { look = [0, 0]; return; }
      // Às vezes volta para o centro, às vezes olha para um ponto qualquer.
      look = Math.random() < 0.3 ? [0, 0] : [(Math.random() * 2 - 1) * range[0], (Math.random() * 2 - 1) * range[1]];
      nextSaccade = t + (state === "ocioso" ? 1.2 + Math.random() * 3 : 0.5 + Math.random() * 1.2);
    }

    function step(dt) {
      const goal = target(currentExpression());
      goal.lookX += look[0];
      goal.lookY += look[1];
      // Mola quase crítica: chega rápido, sem quicar demais (e um pouco de "vida").
      const k = 190;
      const damping = 2 * Math.sqrt(k) * 0.82;
      for (const key in goal) {
        const accel = k * (goal[key] - value[key]) - damping * velocity[key];
        velocity[key] += accel * dt;
        value[key] += velocity[key] * dt;
      }
      levelSmooth += (level - levelSmooth) * Math.min(1, dt * 18);
    }

    function eyes(t) {
      const blink = blinkAmount(t);
      const breathe = reduced ? 0 : Math.sin(t * Math.PI * 0.5) * 0.012;
      const speak = state === "falando" ? levelSmooth : 0;
      return ["L", "R"].map((side) => {
        const eye = {};
        for (const key of KEYS) eye[key] = value[side + key];
        const sign = side === "L" ? -1 : 1;
        // Paralaxe: o olho do lado para onde ele olha cresce um pouco.
        const near = 1 + 0.1 * value.lookX * sign;
        eye.w *= near;
        eye.h *= near * (1 + breathe + speak * 0.14) * (1 - 0.9 * blink);
        eye.cx = sign * EYE_X + value.lookX * 0.32 + eye.dx;
        eye.cy = value.lookY * 0.3 + eye.dy + blink * 0.06 - speak * 0.04;
        eye.inner = -sign; // lado do nariz: +x para o olho esquerdo
        return eye;
      });
    }

    function drawGlyph(glyph, gx, gy, alpha) {
      const { cell, x0, y0, cols, rows } = layout;
      const size = cell * 0.84;
      litCtx.fillStyle = `rgba(${COLOR}, ${alpha})`;
      glyph.forEach((row, y) => {
        [...row].forEach((c, x) => {
          const cx = Math.round(gx) + x;
          const cy = Math.round(gy) + y;
          if (c === "#" && cx >= 0 && cy >= 0 && cx < cols && cy < rows) {
            litCtx.fillRect(x0 + cx * cell + (cell - size) / 2, y0 + cy * cell + (cell - size) / 2, size, size);
          }
        });
      });
    }

    function render(t) {
      const { cell, cols, rows, x0, y0, unit } = layout;
      litCtx.clearRect(0, 0, layout.width, layout.height);
      const size = cell * 0.84;
      const [left, right] = eyes(t);
      const midX = cols / 2;
      const midY = rows / 2;
      const pad = 2;
      for (const eye of [left, right]) {
        // Só percorre as células perto do olho.
        const minX = Math.max(0, Math.floor(midX + (eye.cx - eye.w / 2) * unit) - pad);
        const maxX = Math.min(cols - 1, Math.ceil(midX + (eye.cx + eye.w / 2) * unit) + pad);
        const minY = Math.max(0, Math.floor(midY + (eye.cy - eye.h / 2) * unit) - pad);
        const maxY = Math.min(rows - 1, Math.ceil(midY + (eye.cy + eye.h / 2) * unit) + pad);
        for (let y = minY; y <= maxY; y++) {
          for (let x = minX; x <= maxX; x++) {
            const px = (x + 0.5 - midX) / unit - eye.cx;
            const py = (y + 0.5 - midY) / unit - eye.cy;
            const coverage = Math.min(1, Math.max(0, 0.5 - eyeDistance(px, py, eye, eye.inner) * unit));
            if (coverage < 0.03) continue;
            litCtx.fillStyle = `rgba(${COLOR}, ${coverage.toFixed(3)})`;
            litCtx.fillRect(x0 + x * cell + (cell - size) / 2, y0 + y * cell + (cell - size) / 2, size, size);
          }
        }
      }
      renderExtras(t, right);
      ctx.clearRect(0, 0, layout.width, layout.height);
      ctx.drawImage(grid, 0, 0);
      if (glow) {
        ctx.filter = `blur(${Math.max(2, cell * 0.9)}px)`;
        ctx.globalAlpha = 0.55;
        ctx.drawImage(lit, 0, 0);
        ctx.filter = "none";
        ctx.globalAlpha = 1;
      }
      ctx.drawImage(lit, 0, 0);
    }

    function renderExtras(t, right) {
      const { cols, rows, unit } = layout;
      const midX = cols / 2;
      const midY = rows / 2;
      const expression = currentExpression();
      // zZz subindo enquanto dorme.
      if (state === "dormindo" && !reduced && t >= nextZ) {
        zzz.push({ born: t, big: zzz.length % 2 === 0 });
        nextZ = t + 1.4;
      }
      zzz = zzz.filter((z) => t - z.born < 3.2);
      for (const z of zzz) {
        const age = (t - z.born) / 3.2;
        const gx = midX + (right.cx + right.w * 0.35) * unit + age * unit * 0.45;
        const gy = midY + (right.cy - 0.2) * unit - 5 - age * unit * 0.7;
        drawGlyph(GLYPHS[z.big ? "z5" : "z4"], gx, gy, Math.sin(age * Math.PI) * 0.9);
      }
      if (state !== "dormindo") zzz = [];
      // "?" quando confuso.
      if (expression === "confuso") {
        const bob = reduced ? 0 : Math.sin(t * 3) * 0.6;
        drawGlyph(GLYPHS["?"], midX + (right.cx + right.w * 0.45) * unit, midY + (right.cy - right.h / 2) * unit - 8 + bob, 0.85);
      }
      // Três pontinhos "carregando" enquanto pensa.
      if (expression === "pensando") {
        for (let i = 0; i < 3; i++) {
          const phase = reduced ? 0.5 : (Math.sin(t * 5 - i * 0.7) + 1) / 2;
          drawGlyph(["##", "##"], midX - 4 + i * 3, midY + 0.78 * unit - phase * 1.2, 0.35 + phase * 0.6);
        }
      }
    }

    function frame() {
      raf = requestAnimationFrame(frame);
      const t = now();
      const dt = Math.min(0.05, t - last);
      last = t;
      resize();
      updateLook(t);
      step(dt);
      render(t);
    }

    function start() {
      if (!raf) { last = now(); raf = requestAnimationFrame(frame); }
    }

    function stop() {
      cancelAnimationFrame(raf);
      raf = 0;
    }

    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    start();

    return {
      get state() { return state; },
      setState(name) {
        if (!EXPRESSIONS[name]) {
          console.warn(`BionyFace: estado desconhecido "${name}"`);
          return;
        }
        if (name !== state) reaction = null;
        state = name;
        nextSaccade = 0;
        if (name !== "falando") level = 0;
      },
      react(name, ms = 2200) {
        if (!EXPRESSIONS[name]) {
          console.warn(`BionyFace: reação desconhecida "${name}"`);
          return;
        }
        if (name === "neutro") { reaction = null; return; }
        reaction = { name, until: ms > 0 ? now() + ms / 1000 : Infinity };
      },
      setLevel(v) { level = Math.max(0, Math.min(1, v)); },
      poke() {
        reaction = { name: "surpreso", until: now() + 0.35 };
        setTimeout(() => { reaction = { name: "feliz", until: now() + 1.2 }; }, 350);
      },
      blink() { nextBlink = 0; },
      destroy: stop,
    };
  }

  window.BionyFace = { create, expressions: Object.keys(EXPRESSIONS) };
})();
