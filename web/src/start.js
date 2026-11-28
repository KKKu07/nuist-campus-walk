// 开始界面：选角色（男生 / 女生，实时换上场景里的小人，镜头转到正面）+ 选玩法（跟着路线游览 / 自由逛）。
import './start.css';
import { h } from './phone/ui.js';
import { AVATARS } from './avatar.js';

export function showStartMenu({ rig, P, avatar, isTouch, stunts, onStart }) {
  const prev = { dist: P.dist, pitch: P.pitch };
  P.dist = 4.2; P.pitch = -0.06;
  avatar.rotation.y = P.yaw + Math.PI;   // face the camera while choosing
  const chars = Object.entries(AVATARS).map(([k, a]) => h('button', { class: `sm-char${rig.kind === k ? ' on' : ''}`, 'data-k': k, onclick: () => pick(k) },
    h('i', { style: `background:${a.top}` }, k === 'boy' ? '男' : '女'), h('span', {}, a.name)));
  function pick(k) { rig.setKind(k); chars.forEach((b) => b.classList.toggle('on', b.dataset.k === k)); }
  const el = h('div', { id: 'startMenu' }, h('div', { class: 'sm-card' },
    h('h1', {}, '云游南信大'),
    h('p', { class: 'sm-sub' }, '1:1 复原南京信息工程大学校园'),
    h('h3', {}, '选择角色'),
    h('div', { class: 'sm-chars' }, chars),
    h('h3', {}, '怎么逛'),
    h('button', { class: 'sm-go primary', onclick: () => go('route') }, h('b', {}, '跟着路线游览（推荐）'), h('span', {}, '步行 → 坐校园小公交 → 扫码骑 7ma，约 8 分钟走完')),
    h('button', { class: 'sm-go', onclick: () => go('free') }, h('b', {}, '自由逛校园'), h('span', {}, '地图传送、云游打卡、手机接单、食堂点餐')),
    h('p', { class: 'sm-keys' }, isTouch ? `左下摇杆走路 · 右侧滑动转视角 · “上车/骑”按钮上车骑车${stunts ? ' · 骑车时“飙车”“翘头”键' : ''}` : `WASD 走 · Shift 跑 · 鼠标转视角 · E 上车/骑车 · Tab 手机 · M 地图${stunts ? ' · 骑车时 Shift 飙车、空格翘头' : ''}`)));
  document.body.append(el);
  document.body.classList.add('menu-on');
  // keep the game keys away from the world while the menu is up (registered before the phone's own listener)
  const block = (e) => {
    if (e.code === 'Enter') { e.preventDefault(); go('route'); return; }
    if (e.code === 'Digit1') pick('boy');
    if (e.code === 'Digit2') pick('girl');
    e.preventDefault(); e.stopImmediatePropagation();
  };
  addEventListener('keydown', block, true);
  let closed = false;
  function go(mode) {
    if (closed) return;
    closed = true;
    removeEventListener('keydown', block, true);
    el.remove();
    document.body.classList.remove('menu-on');
    P.dist = prev.dist; P.pitch = prev.pitch; avatar.rotation.y = P.yaw;
    onStart(mode);
  }
  return { close: go };
}
