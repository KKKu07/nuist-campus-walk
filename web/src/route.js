// 路线游览：一条从头走到尾的校园游览路线——步行 → 等车坐校园小公交 → 下车步行 → 扫码骑 7ma → 还车步行，
// 每到一处弹出讲解卡片（官网楼名 / 站名 + 实拍照片），终点给出用时和步行 / 乘车 / 骑行统计。数据：web/public/data/route.json。
// 为了演示不用干等：走到站牌后，小公交会“马上到站”（约 30 秒），到站后在这一站多停一会儿等你上车。
import * as THREE from 'three';
import './route.css';
import { h, mmss } from './phone/ui.js';
import { makeTargets } from './phone/geo.js';

const ICON = { walk: '🚶', bus: '🚌', ebike: '🛵' };

export function createRoute(ctx) {
  const { P, say, scene, heightAt, getBus, getEbikes } = ctx;
  const { tgt, tdist, beaconAt } = makeTargets(ctx);
  let data = null, active = false, i = -1, st = null, T = null, clock = 0, startT = 0, hudT = 0, cardT = 0, scanT = 0;
  let boardedAt = '', lx = 0, lz = 0, summonT = -99, arrived = false, stopName = '', waitedSaid = false;
  const stats = { walk: 0, ride: 0, stops: 0 };

  fetch('data/route.json').then((r) => r.json()).then((d) => { data = d; }).catch((e) => console.warn('route.json', e));

  // orange beacon (打卡 is yellow, phone jobs are blue)
  const beamMat = new THREE.MeshBasicMaterial({ color: '#ff8450', transparent: true, opacity: 0.32, depthWrite: false, side: THREE.DoubleSide, fog: false });
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 90, 16, 1, true).translate(0, 45, 0), beamMat);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.28, 8, 40).rotateX(Math.PI / 2), new THREE.MeshBasicMaterial({ color: '#ff8450' }));
  beam.visible = ring.visible = false;
  scene.add(beam, ring);
  const setBeacon = (x, z) => { const y = heightAt(x, z); beam.position.set(x, y, z); ring.position.set(x, y + 2.2, z); beam.visible = ring.visible = true; };

  // HUD
  const nEl = h('b'), mEl = h('i', { class: 'rb-mode' }), tEl = h('span', { class: 'rb-title' }), aEl = h('i', { class: 'rb-arrow' }, '↑'), dEl = h('span', { class: 'rb-dist' });
  const bar = h('div', { id: 'routeBar', hidden: true }, nEl, mEl, tEl, aEl, dEl, h('button', { title: '结束路线', 'aria-label': '结束路线', onclick: () => stop() }, '×'));
  const cImg = h('img', { alt: '' }), cTitle = h('b'), cText = h('p');
  const card = h('div', { id: 'routeCard', hidden: true }, cImg, h('div', { class: 'rc-body' }, cTitle, cText),
    h('button', { class: 'rc-x', 'aria-label': '关闭', onclick: () => { card.hidden = true; } }, '×'));
  const done = h('div', { id: 'routeDone', hidden: true });
  document.body.append(bar, card, done);

  let cardQ = [], cardAge = 99;
  function showCard(s) { cardQ.push({ s, T }); if (cardAge > 5 || card.hidden) popCard(); }
  function popCard() {
    const it = cardQ.shift();
    if (!it) return;
    const { s } = it, T = it.T;
    cardAge = 0;
    const photo = s.photo || T?.meta?.photos?.[0]?.file;
    cImg.hidden = !photo; if (photo) cImg.src = photo;
    cTitle.textContent = s.type === 'stop' ? `${s.stop}站` : s.target || s.title;
    cText.textContent = s.card;
    card.hidden = false; cardT = 14;
  }
  const busStop = (name) => getBus()?.stops.find((s) => s.name === name) || null;

  function enter() {
    st = data.steps[i]; arrived = false; T = null; waitedSaid = false; beam.visible = ring.visible = false;
    if (st.target) T = tgt(st.target);
    if (st.type === 'ride' && T) {   // ride to the 7ma parking point beside the target, so returning the bike costs no dispatch fee
      const s = ctx.station?.(T.x, T.z);
      if (s && s.d < 150) T = { name: `${st.target}旁 7ma 停车点`, meta: null, x: s.x, z: s.z };
    }
    if (st.type === 'stop') {
      const s = busStop(stopName || st.stop);
      if (s) T = { name: `${s.name}站`, meta: null, x: s.x, z: s.z };
    }
    if (T) { const [x, z] = beaconAt(T, P.pos.x, P.pos.z); setBeacon(x, z); }
    if (st.card && (st.show === 'enter' || st.type === 'stop')) showCard(st);
    if (st.type !== 'intro') say(`第 ${i + 1}/${data.steps.length} 步：${st.title}`, 3);
    if (st.type === 'intro') { i++; enter(); }   // the intro card stays up while the first real step starts
    hudT = 0;
  }
  function complete() {
    if (st.card && st.show !== 'enter' && st.type !== 'stop') showCard(st);
    stopName = '';
    i++;
    if (i >= data.steps.length) finish(); else enter();
  }
  function back(toType, msg) {   // fell out of a step (got off early, parked too soon): redo the previous one
    say(msg, 4);
    while (i > 0 && data.steps[i].type !== toType) i--;
    enter();
  }
  // bring the campus bus to this stop now: ~230 m up the loop, so it pulls in within half a minute
  function summon(idx) {
    const b = getBus(), s = b.stops[idx];
    b.s = ((s.s - 230) % b.len + b.len) % b.len; b.next = idx; b.wait = 0; b.v = 6;
    summonT = clock;
  }

  function finish() {
    active = false; beam.visible = ring.visible = false; bar.hidden = true; card.hidden = true; cardQ = [];
    document.body.classList.remove('route-on');
    const q = ctx.quest?.(), t = clock - startT, last = data.steps.at(-1);
    const stat = (k, v) => h('div', {}, h('b', {}, v), h('span', {}, k));
    done.replaceChildren(h('div', { class: 'rd-card' },
      last?.photo ? h('img', { class: 'rd-img', src: last.photo, alt: last.target || '' }) : null,
      h('h2', {}, '游览完成！'),
      last?.card ? h('p', { class: 'rd-last' }, last.card) : null,
      h('p', {}, `你用 ${mmss(t)} 走完了「${data.title}」${data.summary ? `：${data.summary}` : ''}。`),
      h('div', { class: 'rd-stats' }, stat('步行', `${Math.round(stats.walk)} m`), stat('坐小公交', `${Math.max(1, stats.stops)} 站`),
        stat('骑 7ma', `${(stats.ride / 1000).toFixed(2)} km`), stat('云游打卡', q ? `${q.count}/${q.total}` : '-')),
      h('p', { class: 'rd-note' }, '接下来可以自由逛：M 打开地图传送，J 看打卡册，Tab 用手机接单、去食堂点餐。'),
      h('div', { class: 'rd-btns' },
        h('button', { onclick: () => { done.hidden = true; ctx.goHome?.(); start(); } }, '再走一遍'),
        h('button', { class: 'primary', onclick: () => { done.hidden = true; say('自由逛校园：M 地图、J 打卡册、Tab 手机', 4); } }, '自由逛校园'))));
    done.hidden = false;
    document.exitPointerLock?.();
  }

  function start() {
    if (!data || !getBus()) { say('路线数据加载中，稍等再试', 2); return; }
    active = true; i = 0; startT = clock; stopName = '';
    stats.walk = stats.ride = stats.stops = 0;
    lx = P.pos.x; lz = P.pos.z;
    done.hidden = true; bar.hidden = false;
    document.body.classList.add('route-on');
    enter();
  }
  function stop() {
    if (!active) return;
    active = false; beam.visible = ring.visible = false; bar.hidden = true; card.hidden = true;
    document.body.classList.remove('route-on');
    say('已结束路线游览，可以自由逛（手机 → 任务 里可以重新开始）', 4);
  }

  function drawBar() {
    const b = getBus();
    nEl.textContent = `${i + 1}/${data.steps.length}`;
    mEl.textContent = ICON[st.mode] || '';
    if (st.type === 'bus') {
      tEl.textContent = P.ride === 'bus' ? `坐小公交 · 下一站「${b.nextStop()}」· 在「${st.to}」下车` : st.title;
      aEl.hidden = true; dEl.textContent = '';
      return;
    }
    tEl.textContent = st.title;
    const tx = beam.visible ? beam.position.x : T?.x, tz = beam.visible ? beam.position.z : T?.z;
    if (tx === undefined) { aEl.hidden = true; dEl.textContent = ''; return; }
    const d = T ? tdist(T, P.pos.x, P.pos.z) : Math.hypot(tx - P.pos.x, tz - P.pos.z);
    const ang = Math.atan2(-(tx - P.pos.x), -(tz - P.pos.z)) - P.yaw;
    aEl.hidden = false; aEl.style.transform = `rotate(${-ang}rad)`;
    dEl.textContent = d > 1000 ? `${(d / 1000).toFixed(1)} km` : `${Math.round(d)} m`;
  }

  function update(dt) {
    clock += dt;
    cardAge += dt;
    if (cardQ.length && (cardAge > 5 || card.hidden)) popCard();
    if (cardT > 0 && (cardT -= dt) <= 0) card.hidden = true;
    if (ring.visible) { ring.rotation.y = clock; ring.position.y = beam.position.y + 2.2 + Math.sin(clock * 2) * 0.3; }
    if (!active || !data) return;
    const d = Math.hypot(P.pos.x - lx, P.pos.z - lz);
    lx = P.pos.x; lz = P.pos.z;
    if (d < 20 && !P.fly) { if (P.ride === 'ebike' || P.ride === 'bike') stats.ride += d; else if (!P.ride) stats.walk += d; }
    const b = getBus();

    if (st.type === 'walk') {
      if (!P.fly && P.ride !== 'bus' && T && tdist(T, P.pos.x, P.pos.z) < 12) complete();
    } else if (st.type === 'stop') {
      if (P.ride === 'bus') { boardedAt = stopName || st.stop; complete(); return; }
      const s = busStop(stopName || st.stop);
      if (s && b && !P.fly && Math.hypot(s.x - P.pos.x, s.z - P.pos.z) < 18) {
        const idx = b.stops.indexOf(s), ahead = ((s.s - b.s) % b.len + b.len) % b.len;
        const atStop = Math.hypot(b.x - s.x, b.z - s.z) < 14 && b.v < 0.5;
        const coming = b.next === idx && ahead < 450;
        if (!coming && !atStop && clock - summonT > 6 && Math.hypot(b.x - P.pos.x, b.z - P.pos.z) > 60) summon(idx);
        if (b.justArrived === s.name) b.wait = Math.max(b.wait, 25);
        if (!waitedSaid) { waitedSaid = true; say('到站牌了，小公交马上进站，车停稳后按 E 上车', 4); }
      }
    } else if (st.type === 'bus') {
      if (P.ride === 'bus') {
        if (!arrived && b.wait > 3 && b.v === 0) b.wait = 2;   // on board: don't sit out the long boarding hold
        if (b.justArrived && b.justArrived !== boardedAt) {
          stats.stops++;
          if (b.justArrived === st.to) { arrived = true; b.wait = Math.max(b.wait, 20); say(`到站：${st.to}，按 E 下车`, 8); }
        }
      } else if (arrived) complete();
      else {
        let near = null, nd = Infinity;   // got off early: wait for the next bus at the stop right here
        for (const s of b.stops) { const dd = Math.hypot(s.x - P.pos.x, s.z - P.pos.z); if (s.name !== st.to && dd < nd) { nd = dd; near = s; } }
        stopName = near?.name || '';
        back('stop', `还没到「${st.to}」站，在「${stopName}」站等下一班车`);
      }
    } else if (st.type === 'ebike') {
      if (P.ride === 'ebike') { complete(); return; }
      if ((scanT -= dt) <= 0) {   // beacon on the nearest free 7ma
        scanT = 0.5;
        const eb = getEbikes();
        let bi = -1, bd = Infinity;
        eb?.list.forEach((e, k) => { if (!e.used) { const dd = Math.hypot(e.x - P.pos.x, e.z - P.pos.z); if (dd < bd) { bd = dd; bi = k; } } });
        if (bi >= 0) { const e = eb.list[bi]; T = { name: '7ma', meta: null, x: e.x, z: e.z }; setBeacon(e.x, e.z); }
      }
    } else if (st.type === 'ride') {
      const dd = tdist(T, P.pos.x, P.pos.z), point = !T.meta;
      if (P.ride === 'ebike') { if (dd < (point ? 14 : 60) && !arrived) { arrived = true; say(`到${T.name}了，${ctx.isTouch ? '点「还车」' : '按 E 还车'}`, 6); } }
      else if (!P.ride || P.ride === 'bike') {
        if (dd < (point ? 40 : 90)) complete();
        else back('ebike', '车还没骑到地方哦，再扫一辆 7ma 继续骑');
      }
    }
    if ((hudT -= dt) <= 0 && active) { hudT = 0.2; drawBar(); }
  }

  // shown in the bottom prompt when nothing more specific (上车 / 骑车) applies
  function prompt() {
    if (!active || !st) return '';
    const b = getBus();
    if (st.type === 'stop') {
      const s = busStop(stopName || st.stop);
      if (!s || Math.hypot(s.x - P.pos.x, s.z - P.pos.z) > 18) return '';
      const ahead = ((s.s - b.s) % b.len + b.len) % b.len;
      return Math.hypot(b.x - s.x, b.z - s.z) < 14 ? '小公交进站了，走到车门旁按 E 上车' : `小公交约 ${Math.max(3, Math.round(ahead / 7))} 秒后到站，在站牌旁等候`;
    }
    if (st.type === 'ebike') return '走到橙色光柱下的 7ma 旁按 E 扫码解锁';
    return '';
  }

  return {
    update, prompt, start, stop,
    get active() { return active; },
    get title() { return data?.title || '校园游览路线'; },
    get stepTitle() { return st?.title || ''; },
  };
}
