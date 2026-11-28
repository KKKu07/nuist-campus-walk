// 相机：拍照模式（隐藏 HUD、取景框、滚轮变焦、空格快门），照片加水印存 IndexedDB 相册（最多 30 张），可保存到本机。
import { h, hhmm } from './ui.js';

const DB = 'nuist-album', ST = 'photos', MAX = 30;
let dbp = null;
const db = () => (dbp ||= new Promise((res, rej) => {
  const r = indexedDB.open(DB, 1);
  r.onupgradeneeded = () => r.result.createObjectStore(ST, { keyPath: 'id' });
  r.onsuccess = () => res(r.result);
  r.onerror = () => rej(r.error);
}));
const tx = async (mode, fn) => {
  const d = await db();
  return new Promise((res, rej) => {
    const t = d.transaction(ST, mode), r = fn(t.objectStore(ST));
    t.oncomplete = () => res(r?.result);
    t.onerror = () => rej(t.error);
  });
};
const all = () => tx('readonly', (s) => s.getAll());

export function createCamera({ renderer, scene, camera, P, say, placeName }) {
  let active = false, prevFirst = false, urls = [];
  const flash = h('div', { class: 'pu-flash' });
  const ui = h('div', { id: 'photoUI', hidden: true },
    h('div', { class: 'pu-frame' }, h('i', { class: 'tl' }), h('i', { class: 'tr' }), h('i', { class: 'bl' }), h('i', { class: 'br' })),
    h('div', { class: 'pu-tip' }, '空格 / 点快门拍照 · 滚轮变焦 · V 第一/第三人称 · Esc 退出'),
    h('button', { class: 'pu-shot', 'aria-label': '拍照', onclick: () => shoot() }),
    h('button', { class: 'pu-exit', onclick: () => exit() }, '退出相机'),
    flash);
  document.body.append(ui);
  renderer.domElement.addEventListener('wheel', (e) => {
    if (!active) return;
    camera.fov = Math.max(15, Math.min(75, camera.fov * (e.deltaY > 0 ? 1.08 : 0.93)));
    camera.updateProjectionMatrix();
  }, { passive: true });

  function enter() {
    if (active) return;
    active = true; prevFirst = P.first; P.first = true;
    ui.hidden = false; document.body.classList.add('photo-mode');
  }
  function exit() {
    if (!active) return;
    active = false; P.first = prevFirst;
    camera.fov = 60; camera.updateProjectionMatrix();
    ui.hidden = true; document.body.classList.remove('photo-mode');
  }

  function shoot() {
    renderer.render(scene, camera);   // fresh frame (no AO pass) so the drawing buffer is valid right now
    const src = renderer.domElement, w = Math.min(1600, src.width), ht = Math.round(src.height * w / src.width);
    const c = document.createElement('canvas');
    c.width = w; c.height = ht;
    const x = c.getContext('2d');
    x.drawImage(src, 0, 0, w, ht);
    const place = placeName(P.pos.x, P.pos.z), d = new Date();
    const fs = Math.max(14, Math.round(w / 52));
    x.fillStyle = 'rgba(0,0,0,.35)'; x.fillRect(0, ht - fs * 2.2, w, fs * 2.2);
    x.font = `${fs}px "PingFang SC", "Microsoft YaHei", sans-serif`; x.fillStyle = '#fff';
    x.fillText(`云游南信大 · ${place} · ${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()} ${hhmm(d)}`, fs, ht - fs * 0.75);
    flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go');
    c.toBlob(async (blob) => {
      try {
        await tx('readwrite', (s) => s.put({ id: Date.now(), t: Date.now(), place, blob }));
        const list = (await all()).sort((a, b) => b.t - a.t);
        for (const p of list.slice(MAX)) await tx('readwrite', (s) => s.delete(p.id));
        say(`已存入相册：${place}（手机 → 相机）`, 3);
      } catch { say('这个浏览器不能保存照片', 3); }
    }, 'image/jpeg', 0.88);
  }

  async function renderAlbum(box, open) {
    urls.forEach((u) => URL.revokeObjectURL(u)); urls = [];
    let list;
    try { list = (await all()).sort((a, b) => b.t - a.t); } catch { box.replaceChildren(h('p', { class: 'ph-tip' }, '这个浏览器不能保存照片')); return; }
    if (!box.isConnected) return;
    box.replaceChildren(list.length
      ? h('div', { class: 'al-grid' }, list.map((p) => {
        const u = URL.createObjectURL(p.blob); urls.push(u);
        return h('button', { class: 'al-th', onclick: () => open({ id: p.id, url: u, place: p.place, t: p.t }) }, h('img', { src: u, alt: p.place }));
      }))
      : h('p', { class: 'ph-tip' }, '还没有照片。点“拍照”，走到喜欢的地方按空格。'));
  }

  return {
    get active() { return active; },
    enter, exit, renderAlbum,
    remove: (id) => tx('readwrite', (s) => s.delete(id)),
    key(e) {
      if (e.code === 'Space' || e.code === 'Enter') { if (!e.repeat) shoot(); return true; }
      if (e.code === 'Escape' || e.code === 'Tab') { exit(); return true; }
      return false;
    },
  };
}
