// Procedural canvas textures: building facades (per style), roads, paving, ground detail, water normals, bus livery.
import * as THREE from 'three';
import { GROUND } from './palette.js';

function canvasTex(w, h, draw, { srgb = true, aniso = 8, repeat = true } = {}) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const x = c.getContext('2d');
  draw(x, w, h);
  const t = new THREE.CanvasTexture(c);
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = aniso;
  return t;
}

// night windows: every window (connected blob of pixels where isWin) becomes randomly off / dim / lit,
// written into imageData as a grey emissive mask
export function litWindows(img, W, H, isWin, seed) {
  const n = W * H, on = new Uint8Array(n), lab = new Int16Array(n).fill(-1), r = rng(seed), d = img.data, px4 = [0, 0, 0];
  for (let i = 0; i < n; i++) { px4[0] = d[i * 4]; px4[1] = d[i * 4 + 1]; px4[2] = d[i * 4 + 2]; on[i] = isWin(px4) ? 1 : 0; }
  const stack = [];
  for (let i = 0; i < n; i++) {
    if (!on[i] || lab[i] >= 0) continue;
    const u = r(), v = u < 0.32 ? 0 : u < 0.6 ? 110 : 255;
    lab[i] = v; stack.push(i);
    while (stack.length) {
      const k = stack.pop(), x = k % W, y = (k / W) | 0;
      if (x > 0 && on[k - 1] && lab[k - 1] < 0) { lab[k - 1] = v; stack.push(k - 1); }
      if (x < W - 1 && on[k + 1] && lab[k + 1] < 0) { lab[k + 1] = v; stack.push(k + 1); }
      if (y > 0 && on[k - W] && lab[k - W] < 0) { lab[k - W] = v; stack.push(k - W); }
      if (y < H - 1 && on[k + W] && lab[k + W] < 0) { lab[k + W] = v; stack.push(k + W); }
    }
  }
  for (let i = 0; i < n; i++) { const v = on[i] ? lab[i] : 0; d[i * 4] = d[i * 4 + 1] = d[i * 4 + 2] = v; }
}

// deterministic noise
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

// ---------------------------------------------------------------- facades
// One texture cell = one window bay: 3.2 m wide, 3.6 m tall (one floor). v = 0 is the floor line.
// Each style is drawn twice: colour map (walls white so the vertex colour tints them) and roughness map.
const CW = 256, CH = 288;

function glassGrad(x, y0, y1, a = '#61798d', b = '#2a3947') {
  const g = x.createLinearGradient(0, y0, 0, y1);
  g.addColorStop(0, a); g.addColorStop(1, b);
  return g;
}

const STYLES = {
  modern(x, rough) {
    x.fillStyle = rough ? '#e6e6e6' : '#ffffff'; x.fillRect(0, 0, CW, CH);
    x.fillStyle = rough ? '#d0d0d0' : '#e1e1df'; x.fillRect(0, CH - 26, CW, 26);          // floor slab band
    x.fillStyle = rough ? '#c8c8c8' : '#d4d7da'; x.fillRect(26, 50, 204, 168);            // frame
    x.fillStyle = rough ? '#262626' : glassGrad(x, 54, 214); x.fillRect(32, 56, 192, 156);
    x.fillStyle = rough ? '#c8c8c8' : '#d4d7da'; x.fillRect(124, 56, 8, 156); x.fillRect(32, 120, 192, 5);
  },
  dorm(x, rough) {
    x.fillStyle = rough ? '#e6e6e6' : '#ffffff'; x.fillRect(0, 0, CW, CH);
    x.fillStyle = rough ? '#d0d0d0' : '#e4e1dc'; x.fillRect(0, CH - 22, CW, 22);
    x.fillStyle = rough ? '#c8c8c8' : '#d9dad8'; x.fillRect(40, 60, 128, 150);
    x.fillStyle = rough ? '#262626' : glassGrad(x, 64, 206, '#6a7f90', '#33424f'); x.fillRect(46, 66, 116, 138);
    x.fillStyle = rough ? '#c8c8c8' : '#d9dad8'; x.fillRect(100, 66, 6, 138);
    x.fillStyle = rough ? '#bbbbbb' : '#f4f4f2'; x.fillRect(180, 150, 54, 40);              // AC unit
    x.fillStyle = rough ? '#999999' : '#c9c9c6'; for (let i = 0; i < 5; i++) x.fillRect(184, 156 + i * 7, 46, 2);
    x.fillStyle = rough ? '#888888' : '#9aa0a4'; x.fillRect(40, 170, 128, 4);              // rail
  },
  classical(x, rough) {
    x.fillStyle = rough ? '#e6e6e6' : '#ffffff'; x.fillRect(0, 0, CW, CH);
    x.fillStyle = rough ? '#d6d6d6' : '#efe9de'; x.fillRect(0, 0, 18, CH); x.fillRect(CW - 18, 0, 18, CH);   // pilasters
    x.fillStyle = rough ? '#cccccc' : '#e8e1d3'; x.fillRect(0, CH - 30, CW, 30);
    x.fillStyle = rough ? '#c8c8c8' : '#f7f4ee';
    x.beginPath(); x.moveTo(70, 236); x.lineTo(70, 110); x.arc(128, 110, 58, Math.PI, 0); x.lineTo(186, 236); x.closePath(); x.fill();
    x.fillStyle = rough ? '#262626' : glassGrad(x, 60, 230, '#5d6f80', '#283541');
    x.beginPath(); x.moveTo(80, 228); x.lineTo(80, 112); x.arc(128, 112, 48, Math.PI, 0); x.lineTo(176, 228); x.closePath(); x.fill();
    x.fillStyle = rough ? '#c8c8c8' : '#f7f4ee'; x.fillRect(125, 70, 6, 160); x.fillRect(80, 150, 96, 5);
  },
  brick(x, rough) {
    x.fillStyle = rough ? '#ececec' : '#ffffff'; x.fillRect(0, 0, CW, CH);
    if (!rough) {
      x.fillStyle = 'rgba(0,0,0,0.07)';
      for (let y = 0; y < CH; y += 12) { x.fillRect(0, y, CW, 2); for (let i = (y / 12) % 2 ? 0 : 16; i < CW; i += 32) x.fillRect(i, y, 2, 12); }
    }
    x.fillStyle = rough ? '#c8c8c8' : '#efe7da'; x.fillRect(36, 48, 184, 176);
    x.fillStyle = rough ? '#262626' : glassGrad(x, 56, 216, '#5b6e7e', '#27333e'); x.fillRect(44, 56, 168, 160);
    x.fillStyle = rough ? '#c8c8c8' : '#efe7da'; x.fillRect(126, 56, 6, 160); x.fillRect(44, 112, 168, 5);
  },
  glass(x, rough) {
    x.fillStyle = rough ? '#1c1c1c' : glassGrad(x, 0, CH, '#8fb3be', '#3e6470'); x.fillRect(0, 0, CW, CH);
    x.fillStyle = rough ? '#9a9a9a' : '#d8e1e3';
    for (let i = 0; i <= CW; i += 64) x.fillRect(i - 3, 0, 6, CH);
    x.fillRect(0, CH - 30, CW, 30); x.fillRect(0, 130, CW, 4);
  },
  apartment(x, rough) {
    x.fillStyle = rough ? '#e6e6e6' : '#ffffff'; x.fillRect(0, 0, CW, CH);
    x.fillStyle = rough ? '#cfcfcf' : '#dedcd8'; x.fillRect(0, CH - 34, CW, 34);
    for (const x0 of [18, 140]) {
      x.fillStyle = rough ? '#c8c8c8' : '#d7d9db'; x.fillRect(x0, 62, 100, 150);
      x.fillStyle = rough ? '#262626' : glassGrad(x, 66, 208, '#6e8496', '#334351'); x.fillRect(x0 + 5, 66, 90, 142);
    }
    x.fillStyle = rough ? '#999999' : 'rgba(150,170,180,0.55)'; x.fillRect(0, 196, CW, 58);
  },
  hall(x, rough) {
    x.fillStyle = rough ? '#e6e6e6' : '#ffffff'; x.fillRect(0, 0, CW, CH);
    x.fillStyle = rough ? '#222222' : glassGrad(x, 40, 250, '#7d98a8', '#33505e'); x.fillRect(0, 40, CW, 210);
    x.fillStyle = rough ? '#c8c8c8' : '#e9ebec'; for (let i = 0; i <= CW; i += 64) x.fillRect(i - 4, 40, 8, 210);
    x.fillRect(0, 140, CW, 5);
  },
};

export function facadeMaterials(aniso) {
  const out = {};
  for (const [name, draw] of Object.entries(STYLES)) {
    const map = canvasTex(CW, CH, (x) => draw(x, false), { aniso });
    const roughnessMap = canvasTex(CW, CH, (x) => draw(x, true), { aniso, srgb: false });
    // night glow: glass (dark in the roughness map) becomes the emissive area
    const emissiveMap = canvasTex(CW, CH, (x) => {
      draw(x, true);
      const img = x.getImageData(0, 0, CW, CH);
      litWindows(img, CW, CH, (p) => p[0] < 90, name.length * 977 + CW);
      x.putImageData(img, 0, 0);
    }, { aniso, srgb: false });
    out[name] = new THREE.MeshStandardMaterial({ map, roughnessMap, roughness: 1, metalness: name === 'glass' ? 0.25 : 0.05,
      vertexColors: true, envMapIntensity: 1.1, emissiveMap, emissive: new THREE.Color('#ffc977'), emissiveIntensity: 0 });
  }
  return out;
}

// ---------------------------------------------------------------- roads & paving
// u runs across the road (0 = left edge), v along it (one texture = 8 m).
const rgbOf = (hex) => { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
const rgbStr = ([r, g, b], k = 1, a = 1) => `rgba(${Math.min(255, r * k) | 0},${Math.min(255, g * k) | 0},${Math.min(255, b * k) | 0},${a})`;
// granite-like salt and pepper: n dots of 1-1.6 px, a third light, two thirds dark
function speckle(x, w, h, r, n, base, amp, a) {
  for (let i = 0; i < n; i++) {
    const k = r() < 0.33 ? 1 + amp * (0.4 + r() * 0.6) : 1 - amp * (0.4 + r() * 0.6), s = 1 + r() * 0.6;
    x.fillStyle = rgbStr(base, k, a); x.fillRect(r() * w, r() * h, s, s);
  }
}
function asphalt(x, w, h, seed) {
  x.fillStyle = GROUND.asphalt; x.fillRect(0, 0, w, h);
  const r = rng(seed);
  for (let i = 0; i < 9000; i++) {
    const v = 60 + r() * 40 | 0;
    x.fillStyle = `rgba(${v},${v},${v + 2},0.35)`;
    x.fillRect(r() * w, r() * h, 1 + r() * 2, 1 + r() * 2);
  }
}
export function roadTextures(aniso) {
  // plain asphalt tiled in world units (8 m); lane markings are separate geometry (world.js addMarkings)
  const main = canvasTex(256, 256, (x, w, h) => {
    asphalt(x, w, h, 3);
    x.fillStyle = 'rgba(20,22,24,0.12)'; x.fillRect(0, 0, w, h);   // newer, darker public-road asphalt
  }, { aniso });
  const minor = canvasTex(256, 256, (x, w, h) => {
    asphalt(x, w, h, 5);
    x.fillStyle = 'rgba(255,255,255,0.05)'; x.fillRect(0, 0, w, h);   // older, paler campus asphalt
  }, { aniso });
  // 地表色板 (palette.js): every paving texture averages to its palette colour, so the ground shader, the road
  // meshes and distant (mip-mapped) views show the same surface colour. 4 m per tile unless noted.
  // light grey granite slabs (plazas, yards, footpaths): 57 x 28.5 cm running bond, joints, salt-and-pepper grain
  const stone = canvasTex(512, 512, (x, w, h) => {
    const base = rgbOf(GROUND.stone), r = rng(31), nx = 7, ny = 14, sw = w / nx, sh = h / ny;
    x.fillStyle = rgbStr(base, 0.8); x.fillRect(0, 0, w, h);
    for (let j = 0; j < ny; j++) for (let i = -1; i < nx; i++) {
      x.fillStyle = rgbStr(base, 0.955 + r() * 0.09); x.fillRect(i * sw + (j % 2 ? sw / 2 : 0) + 1, j * sh + 1, sw - 2, sh - 2);
    }
    speckle(x, w, h, r, 30000, base, 0.28, 0.55);
  }, { aniso });
  const paving = stone;
  const track = canvasTex(128, 128, (x, w, h) => {
    const base = rgbOf(GROUND.soil), r = rng(11);
    x.fillStyle = GROUND.soil; x.fillRect(0, 0, w, h);
    speckle(x, w, h, r, 2500, base, 0.25, 0.5);
  }, { aniso });
  // red permeable brick (campus paths per the official map): 25 x 12.5 cm running bond, sandy joints
  const brick = canvasTex(256, 256, (x, w, h) => {
    const base = rgbOf(GROUND.brick), r = rng(13), bw = 16, bh = 8;
    x.fillStyle = rgbStr(rgbOf(GROUND.stone).map((v, i) => v * 0.45 + base[i] * 0.55), 0.82); x.fillRect(0, 0, w, h);
    for (let y = 0; y < h; y += bh) for (let i = -bw; i < w; i += bw) {
      x.fillStyle = rgbStr(base, 1.0 + (r() - 0.5) * 0.18); x.fillRect(i + ((y / bh) % 2 ? bw / 2 : 0) + 1, y + 1, bw - 2, bh - 2);
    }
    speckle(x, w, h, r, 5000, base, 0.18, 0.4);
  }, { aniso });
  // light sidewalk tiles (main-road sidewalks are white tiles): 30 cm squares, slightly darker joints
  const tile = canvasTex(256, 256, (x, w, h) => {
    const base = rgbOf(GROUND.tile), r = rng(17), n = 13, s2 = w / n;
    x.fillStyle = rgbStr(base, 0.84); x.fillRect(0, 0, w, h);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      x.fillStyle = rgbStr(base, 0.975 + r() * 0.06); x.fillRect(i * s2 + 0.8, j * s2 + 0.8, s2 - 1.6, s2 - 1.6);
    }
    speckle(x, w, h, r, 6000, base, 0.12, 0.45);
  }, { aniso });
  // flat-roof insulation pavers (隔热砖): 0.5 m squares, near-white so vertex colour sets the roof tone; 4 m per tile
  const roof = canvasTex(256, 256, (x, w, h) => {
    x.fillStyle = '#9c9c98'; x.fillRect(0, 0, w, h);
    const r = rng(23), n = 8, s2 = w / n;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const v = 222 + r() * 30 | 0;
      x.fillStyle = `rgb(${v},${v},${v})`; x.fillRect(i * s2 + 1.2, j * s2 + 1.2, s2 - 2.4, s2 - 2.4);
    }
    for (let i = 0; i < 900; i++) { const v = 190 + r() * 60 | 0; x.fillStyle = `rgba(${v},${v},${v},0.35)`; x.fillRect(r() * w, r() * h, 2, 2); }
  }, { aniso });
  return { main, minor, paving, track, brick, tile, roof, stone };
}

// ---------------------------------------------------------------- ground detail (multiplied onto the aerial photo up close)
export function detailTexture(aniso) {
  return canvasTex(512, 512, (x, w, h) => {
    const img = x.createImageData(w, h), r = rng(21);
    const grid = (n) => { const g = []; for (let i = 0; i < n * n; i++) g.push(r()); return g; };
    const octs = [[8, 0.45], [32, 0.3], [128, 0.25]].map(([n, a]) => [n, a, grid(n)]);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      let v = 0;
      for (const [n, a, g] of octs) {
        const fx = i / w * n, fy = j / h * n, x0 = Math.floor(fx), y0 = Math.floor(fy), tx = fx - x0, ty = fy - y0;
        const at = (xx, yy) => g[((yy % n + n) % n) * n + ((xx % n + n) % n)];
        const sx = tx * tx * (3 - 2 * tx), sy = ty * ty * (3 - 2 * ty);
        v += a * ((at(x0, y0) * (1 - sx) + at(x0 + 1, y0) * sx) * (1 - sy) + (at(x0, y0 + 1) * (1 - sx) + at(x0 + 1, y0 + 1) * sx) * sy);
      }
      const c = 150 + v * 105 | 0, o = (j * w + i) * 4;
      img.data[o] = img.data[o + 1] = img.data[o + 2] = c; img.data[o + 3] = 255;
    }
    x.putImageData(img, 0, 0);
  }, { aniso, srgb: false });
}

export function waterNormal() {
  return canvasTex(256, 256, (x, w, h) => {
    const img = x.createImageData(w, h);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      const a = (i / w) * Math.PI * 2, b = (j / h) * Math.PI * 2;
      const dx = Math.cos(a * 3 + b * 2) * 0.35 + Math.cos(a * 7 - b * 5) * 0.2 + Math.sin(a * 11 + b * 13) * 0.1;
      const dy = Math.sin(a * 2 - b * 3) * 0.35 + Math.sin(a * 5 + b * 9) * 0.2 + Math.cos(a * 13 - b * 7) * 0.1;
      const o = (j * w + i) * 4;
      img.data[o] = 128 + dx * 90; img.data[o + 1] = 128 + dy * 90; img.data[o + 2] = 255; img.data[o + 3] = 255;
    }
    x.putImageData(img, 0, 0);
  }, { srgb: false });
}

// ---------------------------------------------------------------- campus bus livery (white body, blue roof and swoosh, see 小公交 photos)
export function busSideTexture() {
  return canvasTex(1024, 256, (x, w, h) => {
    x.fillStyle = '#f7f8f8'; x.fillRect(0, 0, w, h);
    x.fillStyle = '#1e6fc4'; x.fillRect(0, 0, w, 26);
    x.fillStyle = '#26323c'; x.fillRect(120, 40, w - 170, 92);             // window band
    x.fillStyle = '#7f98aa'; for (let i = 140; i < w - 60; i += 118) x.fillRect(i, 46, 104, 80);
    x.fillStyle = '#26323c'; x.fillRect(20, 40, 80, 200);                  // door
    x.fillStyle = '#7f98aa'; x.fillRect(28, 46, 64, 110);
    const g = x.createLinearGradient(0, 150, w, 250);
    g.addColorStop(0, '#1d74cf'); g.addColorStop(1, '#46a7e8');
    x.fillStyle = g;
    x.beginPath(); x.moveTo(110, 256); x.bezierCurveTo(400, 150, 700, 230, w, 150); x.lineTo(w, 256); x.closePath(); x.fill();
    x.fillStyle = 'rgba(70,167,232,0.7)';
    x.beginPath(); x.moveTo(300, 256); x.bezierCurveTo(550, 190, 800, 240, w, 200); x.lineTo(w, 256); x.closePath(); x.fill();
    x.fillStyle = '#1e5aa0'; x.font = 'bold 30px "Microsoft YaHei", sans-serif'; x.fillText('南京信息工程大学', 360, 175);
    x.fillStyle = '#1e5aa0'; x.font = '24px "Microsoft YaHei", sans-serif'; x.fillText('校园公交', 760, 178);
  }, { repeat: false });
}

export function busFrontTexture() {
  return canvasTex(256, 256, (x, w, h) => {
    x.fillStyle = '#f7f8f8'; x.fillRect(0, 0, w, h);
    x.fillStyle = '#1e6fc4'; x.fillRect(0, 0, w, 24);
    x.fillStyle = '#26323c'; x.fillRect(14, 34, w - 28, 112);
    x.fillStyle = '#86a0b2'; x.fillRect(20, 40, w - 40, 100);
    x.fillStyle = '#2a3440'; x.beginPath(); x.arc(52, 200, 16, 0, 7); x.arc(204, 200, 16, 0, 7); x.fill();
    x.fillStyle = '#e8f2ff'; x.beginPath(); x.arc(52, 200, 10, 0, 7); x.arc(204, 200, 10, 0, 7); x.fill();
    x.fillStyle = '#2d9a4f'; x.fillRect(92, 214, 72, 22);
    x.fillStyle = '#ffffff'; x.font = 'bold 14px "Microsoft YaHei", sans-serif'; x.fillText('校园公交', 98, 230);
  }, { repeat: false });
}
