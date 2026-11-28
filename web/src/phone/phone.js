// 手机（Tab）：消息 / 扫一扫 / 钱包·乘车码 / 相机 / 地图 / 任务，外加通知横幅、弹窗宿主，
// 以及给 main.js 的接口：interact / prompt / scanEbike / endEbike / ebikePrompt / payBus / onStamp / allowTravel / update。
// 金额、群聊、人物、菜单都是游戏内容；楼名、食堂名、快递点名来自官网点位。
import './phone.css';
import { h, yuan, hhmm, mmss, ri } from './ui.js';
import { loadState, saveState, freshState } from './store.js';
import { createWallet } from './wallet.js';
import { createTasks } from './tasks.js';
import { createCanteen } from './canteen.js';
import { createCamera } from './camera.js';
import { makeTargets } from './geo.js';

const APPS = [
  { id: 'msgs', name: '消息', icon: '💬', bg: '#2fb45a' },
  { id: 'scan', name: '扫一扫', icon: '🔳', bg: '#2f7de0' },
  { id: 'wallet', name: '钱包', icon: '👛', bg: '#e8a020' },
  { id: 'camera', name: '相机', icon: '📷', bg: '#55606a' },
  { id: 'map', name: '地图', icon: '🗺️', bg: '#2aa198' },
  { id: 'tasks', name: '任务', icon: '📋', bg: '#e0503c' },
];
const EBIKE_START = 1.5, EBIKE_FREE_MIN = 5, EBIKE_PER_MIN = 0.5, EBIKE_DISPATCH = 2, STATION_R = 15, BUS_FARE = 1;

export function createPhone(ctx) {
  const { P, say, markers, named, metas, isTouch } = ctx;
  const S = loadState();
  if (S.task) S.task.left = Math.max(S.task.left, 60);   // a little grace after reloading the page
  const save = () => saveState(S);
  let isOpen = false, cur = { app: 'home' }, stack = [], ride = null, scanning = false;
  let barT = 0, saveT = 0, hungerWarnAt = 0, travelAskT = -99, clock = 0, resetArm = -99;
  let data = null, people = { roommate: '室友·阿杰', classmate: '同学·小林', media: '校园媒体' }, groupName = '信大互助群';

  // targets: a building footprint (by name or by the official marker inside it) or a bare point
  const { tgt, tdist, beaconAt, placeName } = makeTargets({ named, markers, metas, collide: ctx.collide });
  // 7ma 停车点: the original parking spots (campus.json ebikes) clustered within 8 m; returning a bike elsewhere costs a dispatch fee
  const stations = [];
  for (const [x, z] of ctx.ebikeSpots || []) {
    const s = stations.find((o) => Math.hypot(o.x - x, o.z - z) < 8);
    if (s) { s.n++; s.x += (x - s.x) / s.n; s.z += (z - s.z) / s.n; } else stations.push({ x, z, n: 1 });
  }
  function nearestStation(x, z) {
    let best = null, bd = Infinity;
    for (const s of stations) { const d = Math.hypot(s.x - x, s.z - z); if (d < bd) { bd = d; best = s; } }
    return best ? { x: best.x, z: best.z, d: bd } : null;
  }
  const dorms = [...new Set(named.filter((m) => m.kind === 'dorm' && m.campus && m.xs && m.name).map((m) => m.name))].map(tgt).filter(Boolean);

  // ---------- DOM ----------
  const clockEl = h('span'), moneyEl = h('span'), hungerEl = h('span');
  const screen = h('div', { class: 'ph-screen' });
  const root = h('div', { id: 'phone', class: 'ph-off', 'aria-label': '手机' },
    h('div', { class: 'ph-bar' }, clockEl, h('i', { class: 'ph-notch' }), h('span', { class: 'ph-right' }, hungerEl, moneyEl)),
    screen,
    h('div', { class: 'ph-nav' },
      h('button', { onclick: () => back() }, '‹ 返回'),
      h('button', { onclick: () => go({ app: 'home' }, true) }, '主屏'),
      h('button', { onclick: () => hide() }, isTouch ? '收起' : '收起 Tab')));
  const banners = h('div', { id: 'phBanners' });
  const hint = h('div', { id: 'phHint', onclick: () => toggle() }, '📱 Tab 手机');
  const mCard = h('div', { class: 'lm-card' });
  const mHost = h('div', { id: 'lifeModal', hidden: true }, mCard);
  document.body.append(root, banners, hint, mHost);
  const touchBtn = document.querySelector('#tbtns [data-act="phone"]');
  touchBtn?.addEventListener('click', () => toggle());

  // ---------- modal host (canteen, classroom, parcel shelf) ----------
  let mOpts = null;
  const modal = {
    get isOpen() { return !!mOpts; },
    open(node, opts = {}) {
      mOpts = opts; hide();
      mCard.className = `lm-card${opts.wide ? ' wide' : ''}`;
      mCard.replaceChildren(node); mHost.hidden = false;
      document.exitPointerLock?.();
    },
    close() { mOpts = null; mHost.hidden = true; mCard.replaceChildren(); },
    key(e) {
      if (!mOpts) return false;
      if (mOpts.key?.(e)) return true;
      const can = typeof mOpts.canClose === 'function' ? mOpts.canClose() : mOpts.canClose !== false;
      if (e.code === 'Escape' && can) { modal.close(); return true; }
      return false;
    },
  };

  // ---------- chats ----------
  const chatMeta = () => ({
    group: { name: `${groupName}（虚构）`, av: '群', c: '#2fb45a', group: true },
    roommate: { name: people.roommate, av: '杰', c: '#e07a3c' },
    classmate: { name: people.classmate, av: '林', c: '#7d5aa6' },
    media: { name: people.media, av: '媒', c: '#1e6fc4' },
  });
  function banner(title, text, chat) {
    const b = h('div', { class: 'ph-ban', onclick: () => { b.remove(); if (show()) go(chat ? { app: 'chat', arg: chat } : { app: 'msgs' }, true); } },
      h('b', {}, title), h('span', {}, text), h('em', {}, isTouch ? '点这里查看' : 'Tab 查看'));
    banners.prepend(b);
    while (banners.children.length > 3) banners.lastChild.remove();
    setTimeout(() => b.remove(), 5500);
  }
  function post(chat, from, text, extra = {}) {
    const list = (S.chats[chat] ||= []);
    const { quiet, ...rest } = extra;
    const m = { id: S.seq++, from, text, t: Date.now(), ...rest };
    list.push(m);
    if (list.length > 60) list.splice(0, list.length - 60);
    const viewing = isOpen && cur.app === 'chat' && cur.arg === chat;
    if (from !== 'me' && !viewing) {
      S.unread[chat] = (S.unread[chat] || 0) + 1;
      if (!quiet) banner(chatMeta()[chat]?.name || chat, chatMeta()[chat]?.group ? `${from}：${text}` : text, chat);
    }
    save(); refresh(); paintHint();
    return m;
  }

  const wallet = createWallet(S, save, () => paintBar());
  const tasks = createTasks({ ctx, S, save, wallet, post, modal, tgt, tdist, beaconAt, dorms, openApp, refresh: () => refresh() });
  const canteen = createCanteen({ S, save, wallet, modal, tgt, tdist, tasks, say });
  const cam = createCamera({ renderer: ctx.renderer, scene: ctx.scene, camera: ctx.camera, P, say, placeName });

  Promise.all(['data/tasks.json', 'data/menus.json'].map((u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u); return r.json(); })))
    .then(([td, md]) => { data = td; people = { ...people, ...td.people }; groupName = td.group || groupName; tasks.setData(td, md); canteen.setData(md); refresh(); })
    .catch((e) => console.warn('phone data not loaded', e));

  let started = false;   // no job offers / chatter until the start menu closes
  function welcome() {
    started = true;
    if (S.intro) return;
    S.intro = true;
    post('media', people.media, `欢迎来到云游南信大！按 ${isTouch ? '右下“手机”按钮' : 'Tab'} 拿出手机。钱包里有 50 元生活费（游戏内余额），扫码骑 7ma、坐校园小公交都用它付；${ctx.getRoute ? '跟着路线游览时，按顶部提示走就行。' : ''}自由逛的时候可以去「${groupName}」接单挣钱。`);
  }

  // ---------- navigation ----------
  function show() {
    if (ctx.tourActive?.()) { say('导览中不能用手机', 2); return false; }
    if (cam.active || modal.isOpen) return false;
    if (!isOpen) { isOpen = true; root.classList.remove('ph-off'); document.exitPointerLock?.(); }
    render();
    return true;
  }
  function hide() { if (!isOpen) return; isOpen = false; root.classList.add('ph-off'); }
  function toggle() { if (isOpen) hide(); else if (show()) go({ app: 'home' }, true); }
  function go(view, reset) {
    if (reset) stack = []; else stack.push(cur);
    cur = view;
    if (view.app === 'chat') { S.unread[view.arg] = 0; save(); paintHint(); }
    render();
  }
  function back() {
    if (stack.length) { cur = stack.pop(); render(); } else if (cur.app !== 'home') { cur = { app: 'home' }; render(); } else hide();
  }
  function openApp(id) {
    if (id === 'map') { hide(); ctx.openMap?.(); return; }
    if (!isOpen && !show()) return;
    go({ app: id }, cur.app !== 'home');
  }
  function refresh() { if (isOpen && ['home', 'msgs', 'chat', 'wallet', 'tasks'].includes(cur.app)) render(); }

  // ---------- views ----------
  const unreadTotal = () => Object.values(S.unread).reduce((a, b) => a + (b || 0), 0);
  const page = (title, ...kids) => h('div', { class: 'ph-page' }, h('h3', {}, title), ...kids);

  function viewHome() {
    const badge = (id) => {
      const n = id === 'msgs' ? unreadTotal() : id === 'tasks' && tasks.offer && !S.task ? '!' : 0;
      return n ? h('em', {}, String(n)) : null;
    };
    return h('div', { class: 'ph-home' },
      h('div', { class: 'ph-wall' }, h('b', {}, hhmm(Date.now())), h('span', {}, '云游南信大')),
      h('div', { class: 'ph-grid' }, APPS.map((a, i) => h('button', { class: 'ph-app', onclick: () => openApp(a.id), title: isTouch ? a.name : `${a.name}（${i + 1}）` },
        h('i', { style: `background:${a.bg}` }, a.icon, badge(a.id)), h('span', {}, a.name)))),
      S.task ? h('button', { class: 'ph-mini', onclick: () => openApp('tasks') }, h('b', {}, S.task.title), h('span', {}, `${S.task.steps[S.task.step].label} · ${mmss(S.task.left)}`)) : null,
      isTouch ? null : h('p', { class: 'ph-tip' }, '数字键 1–6 打开 App · Esc 返回 · Tab 收起'));
  }

  function viewMsgs() {
    const meta = chatMeta();
    const ids = Object.keys(meta).filter((id) => S.chats[id]?.length).sort((a, b) => S.chats[b].at(-1).t - S.chats[a].at(-1).t);
    return page('消息', ids.length ? h('div', { class: 'ms-list' }, ids.map((id) => {
      const last = S.chats[id].at(-1), n = S.unread[id] || 0;
      return h('button', { class: 'ms-row', onclick: () => go({ app: 'chat', arg: id }) },
        h('i', { style: `background:${meta[id].c}` }, meta[id].av),
        h('div', {}, h('b', {}, meta[id].name), h('span', {}, `${last.from === 'me' ? '我' : meta[id].group ? last.from : ''}${last.from === 'me' || meta[id].group ? '：' : ''}${last.text}`)),
        h('small', {}, hhmm(last.t)), n ? h('em', {}, String(n)) : null);
    })) : h('p', { class: 'ph-tip' }, '还没有消息'), h('p', { class: 'ph-tip' }, '群聊、人物与任务均为虚构的游戏内容'));
  }

  function viewChat(id) {
    const meta = chatMeta()[id], msgs = S.chats[id] || [], offer = tasks.offer;
    const list = h('div', { class: 'ch-list' }, msgs.map((m) => {
      const me = m.from === 'me';
      let extra = null;
      if (m.offer) {
        if (offer && offer.id === m.offer) {
          extra = h('div', { class: 'ch-acts' },
            h('button', { class: 'ph-btn', onclick: () => tasks.accept(m.offer) }, `接单（${yuan(offer.pay)}）`),
            h('button', { class: 'ph-btn ghost', onclick: () => tasks.decline(m.offer) }, '算了'));
        } else extra = h('small', { class: 'ch-state' }, S.task?.id === m.offer ? '已接单' : '已结束');
      }
      return h('div', { class: `ch-msg${me ? ' me' : ''}` },
        !me && meta?.group ? h('small', {}, m.from) : null,
        m.pay ? h('div', { class: 'ch-pay' }, h('b', {}, yuan(m.pay)), h('span', {}, '转账 · 已收款（游戏内）')) : h('div', { class: 'ch-bub' }, m.text),
        extra);
    }));
    requestAnimationFrame(() => { list.scrollTop = list.scrollHeight; });
    return h('div', { class: 'ph-page ch' }, h('h3', {}, meta?.name || id), list);
  }

  function viewScan(arg) {
    const st = arg?.phase;
    return page('扫一扫',
      h('div', { class: `sc-view${st === 'scan' ? ' run' : ''}${st === 'ok' ? ' ok' : ''}` }, h('i'), h('b', {}, st === 'ok' ? '✓' : '')),
      h('p', { class: 'sc-txt' }, st === 'scan' ? `正在识别 7ma 车辆 ${arg.no}…` : st === 'ok' ? `解锁成功 · ${arg.no} · 起步 ${yuan(EBIKE_START)}` : ride ? `骑行中 ${mmss((performance.now() - ride.start) / 1000)}` : '走到 7ma 电动车旁按 E，自动扫码解锁'),
      h('p', { class: 'ph-tip' }, `7ma：起步 ${yuan(EBIKE_START)} 含 ${EBIKE_FREE_MIN} 分钟，之后 ${yuan(EBIKE_PER_MIN)}/分钟；校园小公交 ${yuan(BUS_FARE)}/次（均为游戏内价格）`));
  }

  function qr() {
    const n = 25, c = h('canvas', { width: n * 8, height: n * 8, class: 'bc-qr' }), x = c.getContext('2d');
    x.fillStyle = '#fff'; x.fillRect(0, 0, n * 8, n * 8); x.fillStyle = '#111';
    const finder = (i, k) => i < 7 && k < 7 ? 1 : i < 7 && k >= n - 7 ? 2 : i >= n - 7 && k < 7 ? 3 : 0;
    for (let i = 0; i < n; i++) for (let k = 0; k < n; k++) {
      const f = finder(i, k);
      let on = Math.random() < 0.48;
      if (f) { const a = f === 2 ? k - (n - 7) : k, b = f === 3 ? i - (n - 7) : i; on = a === 0 || a === 6 || b === 0 || b === 6 || (a > 1 && a < 5 && b > 1 && b < 5); }
      if (on) x.fillRect(k * 8, i * 8, 8, 8);
    }
    return c;
  }
  function viewBuscode(arg) {
    return page('乘车码', h('div', { class: 'bc' }, h('b', {}, '南信大校园小公交'), qr(),
      h('span', { class: arg === 'beep' ? 'bc-ok' : '' }, arg === 'beep' ? `嘀——乘车成功 · ${yuan(BUS_FARE)}` : `上车时出示 · ${yuan(BUS_FARE)}/次`)),
    h('p', { class: 'ph-tip' }, '游戏内乘车码，非真实凭证'));
  }

  function viewWallet() {
    return page('钱包',
      h('div', { class: `wl-card${S.money < 0 ? ' neg' : ''}` }, h('span', {}, '游戏内余额'), h('b', {}, `¥ ${S.money.toFixed(2)}`), h('small', {}, '所有金额均为游戏内容')),
      h('button', { class: 'ph-btn', onclick: () => go({ app: 'buscode' }) }, '校园小公交乘车码'),
      h('h4', {}, '账单'),
      S.txns.length ? h('div', { class: 'wl-list' }, S.txns.map((t) => h('div', { class: 'wl-row' },
        h('span', {}, t.title), h('small', {}, hhmm(t.t)), h('b', { class: t.amount > 0 ? 'in' : '' }, `${t.amount > 0 ? '+' : '−'}${yuan(Math.abs(t.amount))}`)))) : h('p', { class: 'ph-tip' }, '还没有收支'));
  }

  function viewCamera() {
    const box = h('div', {}, h('p', { class: 'ph-tip' }, '读取相册…'));
    cam.renderAlbum(box, (p) => go({ app: 'photo', arg: p }));
    return page('相机', h('button', { class: 'ph-btn', onclick: () => { hide(); cam.enter(); } }, '📷 拍照'), h('h4', {}, '相册'), box);
  }
  function viewPhoto(p) {
    const d = new Date(p.t);
    return page(p.place, h('img', { class: 'al-big', src: p.url, alt: p.place }),
      h('p', { class: 'ph-tip' }, `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${hhmm(p.t)}`),
      h('div', { class: 'ch-acts' },
        h('a', { class: 'ph-btn', href: p.url, download: `云游南信大_${p.place}_${p.id}.jpg` }, '保存到本机'),
        h('button', { class: 'ph-btn ghost', onclick: async () => { await cam.remove(p.id); back(); } }, '删除')));
  }

  function viewTasks() {
    const t = S.task, o = tasks.offer, q = ctx.quest?.();
    const stat = (k, v) => h('div', {}, h('b', {}, String(v)), h('span', {}, k));
    const rt = ctx.getRoute?.();
    return page('任务',
      rt ? h('div', { class: 'tk-card on' }, h('b', {}, rt.title), h('span', {}, rt.active ? `进行中：${rt.stepTitle}` : '步行 → 坐小公交 → 扫码骑 7ma，约 8 分钟走完一条游览路线'),
        h('button', { class: rt.active ? 'ph-btn ghost' : 'ph-btn', onclick: () => { hide(); if (rt.active) rt.stop(); else rt.start(); } }, rt.active ? '结束路线' : '开始路线游览')) : null,
      t ? h('div', { class: 'tk-card on' }, h('b', {}, t.title), h('span', {}, t.steps[t.step].label),
        h('small', {}, `剩余 ${mmss(t.left)} · 报酬 ${yuan(t.pay)}`),
        h('button', { class: 'ph-btn ghost', onclick: () => { tasks.abandon(); render(); } }, '放弃任务'))
        : h('div', { class: 'tk-card' }, h('span', {}, o ? '有新单！去消息里接单' : data ? '暂时没有任务，等群里或私聊发单' : '任务数据加载中…'),
          o ? h('button', { class: 'ph-btn', onclick: () => go({ app: 'chat', arg: o.chat }) }, '去看看') : null),
      h('h4', {}, '记录'),
      h('div', { class: 'tk-stats' }, tasks.kinds.includes('class') ? stat('替课', S.stats.class) : null, stat('取快递', S.stats.express), stat('带饭', S.stats.food),
        stat('吃饭', S.stats.meals), stat('累计收入', yuan(S.stats.earned)), ctx.stunt ? stat('翘头最佳', `${ctx.stunt.best.toFixed(1)}s`) : stat('骑 7ma', S.stats.rides)),
      q ? h('div', { class: 'tk-card' }, h('b', {}, `云游打卡 ${q.count}/${q.total}`), h('span', {}, '每盖一个章奖励 ¥5'),
        h('button', { class: 'ph-btn ghost', onclick: () => { hide(); ctx.openBook?.(); } }, '打开打卡册')) : null,
      h('button', { class: 'ph-btn ghost danger', onclick: (e) => {
        if (clock - resetArm > 4) { resetArm = clock; e.currentTarget.textContent = '再点一次确认清空（余额、聊天、记录）'; return; }
        for (const k of Object.keys(S)) delete S[k];
        Object.assign(S, freshState(), { intro: true });
        tasks.reset(); save(); paintBar(); paintHint(); render(); say('手机存档已清空', 2);
      } }, '清空手机存档'));
  }

  function viewReceipt(r) {
    const row = (k, v, cls = '') => h('div', { class: `rc-row ${cls}` }, h('span', {}, k), h('b', {}, v));
    return page('行程账单', h('div', { class: 'rc-card' },
      h('div', { class: 'rc-head' }, h('b', {}, '7ma 共享电动车'), h('span', {}, `车辆 ${r.no} · 已还车`)),
      row('骑行时长', mmss(r.sec)),
      row(`起步价（含 ${EBIKE_FREE_MIN} 分钟）`, yuan(EBIKE_START)),
      r.over > 0 ? row(`超时 ${Math.ceil(r.sec / 60) - EBIKE_FREE_MIN} 分钟`, yuan(r.over)) : null,
      r.dispatch > 0 ? row('停车点外还车 · 调度费', yuan(r.dispatch), 'warn') : row('还车位置', '7ma 停车点内'),
      row('合计', yuan(r.total), 'sum'),
      row('余额', `¥${S.money.toFixed(2)}`)),
    h('p', { class: 'ph-tip' }, '游戏内价格，非 7ma 真实收费。'));
  }

  const VIEWS = { receipt: viewReceipt, home: viewHome, msgs: viewMsgs, chat: viewChat, scan: viewScan, buscode: viewBuscode, wallet: viewWallet, camera: viewCamera, photo: viewPhoto, tasks: viewTasks };
  function render() {
    if (!isOpen) return;
    screen.replaceChildren((VIEWS[cur.app] || viewHome)(cur.arg));
    paintBar();
  }
  function paintBar() {
    clockEl.textContent = hhmm(Date.now());
    moneyEl.textContent = `¥${S.money.toFixed(2)}`;
    moneyEl.className = S.money < 0 ? 'neg' : '';
    hungerEl.textContent = `🍚${Math.round(S.hunger)}%`;
  }
  function paintHint() {
    const n = unreadTotal();
    hint.textContent = n ? `📱 Tab 手机 · ${n} 条未读` : '📱 Tab 手机';
    hint.classList.toggle('new', n > 0);
    if (touchBtn) { touchBtn.classList.toggle('dot', n > 0); }
  }
  paintBar(); paintHint();

  // ---------- keyboard (capture phase, before main.js) ----------
  const stop = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (cam.active) { if (cam.key(e)) stop(e); return; }
    if (modal.isOpen) { modal.key(e); if (!/^(Key[WASD]|Arrow|Shift)/.test(e.code)) stop(e); return; }
    if (e.code === 'Tab') { stop(e); if (!e.repeat) toggle(); return; }
    if (!isOpen) return;
    if (e.code === 'Escape' || e.code === 'Backspace') { stop(e); back(); return; }
    const d = /^Digit([1-6])$/.exec(e.code);
    if (d && cur.app === 'home') { stop(e); openApp(APPS[d[1] - 1].id); }
  }, true);

  // ---------- E interactions in the world ----------
  // level 'high' = job targets (before the bus / 7ma), 'low' = canteens (after them), none = both
  function interactable(level) {
    if (modal.isOpen || cam.active || P.fly || P.ride === 'bus' || P.ride === 'ebike') return null;
    return (level !== 'low' && tasks.interactable()) || (level !== 'high' && canteen.interactable(P.pos)) || null;
  }
  const rideCost = (sec) => EBIKE_START + Math.max(0, Math.ceil(sec / 60) - EBIKE_FREE_MIN) * EBIKE_PER_MIN;

  return {
    state: S, wallet,
    get isOpen() { return isOpen; },
    get busy() { return modal.isOpen; },
    welcome,
    toggle, openApp,
    interact(level) {
      const it = interactable(level);
      if (!it) return false;
      if (P.ride === 'bike') P.ride = null;
      hide(); it.run();
      return true;
    },
    prompt(level) { const it = interactable(level); return it ? it.text : ''; },

    // 7ma: scan to unlock (charged on success), billed by ride time when parked
    scanEbike(onUnlock) {
      if (scanning || ride) return;
      if (!wallet.can(EBIKE_START)) { say(`余额不足（${yuan(S.money)}），7ma 起步 ${yuan(EBIKE_START)}。去群里接单挣点钱吧`, 4); return; }
      const wasOpen = isOpen, no = `NJ${ri(10000, 99999)}`;
      scanning = true;
      if (show()) go({ app: 'scan', arg: { phase: 'scan', no } }, true);
      setTimeout(() => {
        scanning = false;
        if (onUnlock() === false) { if (isOpen && cur.app === 'scan') hide(); say('离车太远，没扫上码，走回车旁再按一次', 3); return; }
        wallet.pay(EBIKE_START, '7ma 起步价（游戏内价格）');
        ride = { start: performance.now(), no }; S.stats.rides++;
        if (isOpen && cur.app === 'scan') { cur.arg = { phase: 'ok', no }; render(); }
        say(`解锁成功 · 起步 ${yuan(EBIKE_START)}（含 ${EBIKE_FREE_MIN} 分钟）${!ctx.stunt ? ` · 到 7ma 停车点再${isTouch ? '点「还车」' : '按 E '}还车` : isTouch ? ' · 飙车键加速 · 按住翘头键翘头' : ' · Shift 飙车 · 按住空格翘头'}`, 4);
        setTimeout(() => { if (!wasOpen && isOpen && cur.app === 'scan') hide(); }, 900);
      }, 1000);
    },
    endEbike() {
      if (!ride) { say('已还车', 2); return; }
      const sec = (performance.now() - ride.start) / 1000, over = rideCost(sec) - EBIKE_START;
      const st = nearestStation(P.pos.x, P.pos.z), dispatch = st && st.d > STATION_R ? EBIKE_DISPATCH : 0;
      if (over > 0) wallet.pay(over, '7ma 超时费（游戏内价格）', true);
      if (dispatch) wallet.pay(dispatch, '7ma 停车点外还车调度费（游戏内价格）', true);
      const r = { no: ride.no, sec, over, dispatch, total: EBIKE_START + over + dispatch };
      ride = null;
      say(`已还车 · 骑行 ${mmss(sec)} · 共 ${yuan(r.total)}${dispatch ? ` · 不在停车点，含调度费 ${yuan(dispatch)}` : ''}${S.money < 0 ? ' · 余额已欠费' : ''}`, 5);
      const wasOpen = isOpen;
      if (show()) go({ app: 'receipt', arg: r }, true);
      setTimeout(() => { if (!wasOpen && isOpen && cur.app === 'receipt') hide(); }, 2600);
    },
    nearestStation,
    ebikePrompt() {
      if (!ride) return '';
      const sec = (performance.now() - ride.start) / 1000, st = nearestStation(P.pos.x, P.pos.z);
      const where = !st ? '' : st.d <= STATION_R ? ' · 在停车点' : ` · 停车点 ${st.d > 1000 ? (st.d / 1000).toFixed(1) + ' km' : Math.round(st.d) + ' m'}`;
      return `骑行 7ma ${mmss(sec)} · ${yuan(rideCost(sec))}${where} · ${isTouch ? '点「还车」' : 'E 还车'}`;
    },
    payBus() {
      if (!wallet.can(BUS_FARE)) { say(`余额不足 ${yuan(BUS_FARE)}，坐不了小公交（${yuan(S.money)}）。去群里接单挣点钱吧`, 4); return false; }
      wallet.pay(BUS_FARE, '校园小公交（游戏内价格）');
      const wasOpen = isOpen;
      if (show()) go({ app: 'buscode', arg: 'beep' }, true);
      setTimeout(() => { if (!wasOpen && isOpen && cur.app === 'buscode') hide(); }, 1400);
      return true;
    },
    onStamp(it, n, total) {
      wallet.earn(5, `打卡奖励 · ${it.name}`);
      post('media', people.media, `打卡「${it.name}」成功（${n}/${total}），奖励 ¥5（游戏内）`, { quiet: true });
    },
    // flying / map teleport / tour while a task runs: ask once, abandon on the second try
    allowTravel() {
      if (!S.task) return true;
      if (clock - travelAskT < 4) { tasks.abandon('travel'); return true; }
      travelAskT = clock;
      say('任务进行中：飞行 / 传送 / 导览会放弃任务，4 秒内再操作一次确认', 4);
      return false;
    },
    update(dt) {
      clock += dt;
      if (!P.fly && !ctx.tourActive?.()) {
        const before = S.hunger;
        S.hunger = Math.max(0, S.hunger - dt / 18);
        if (S.hunger < 25 && before >= 25 || (S.hunger < 25 && clock > hungerWarnAt)) {
          hungerWarnAt = clock + 180;
          say('有点饿了……去中苑新食堂（厚学园）吃点东西吧', 4);
        }
      }
      tasks.update(dt, modal.isOpen && mOpts?.pauseTask, !started || !!ctx.getRoute?.()?.active);
      mOpts?.tick?.(dt);
      if ((barT -= dt) <= 0) {
        barT = 1;
        paintBar();
        root.classList.toggle('dark', !!ctx.isNight?.());
        hint.hidden = isOpen || cam.active;
        if (isOpen && !scanning && (cur.app === 'scan' || cur.app === 'home' || (cur.app === 'tasks' && clock - resetArm > 4))) render();
      }
      if ((saveT += dt) > 5) { saveT = 0; save(); }
    },
  };
}
