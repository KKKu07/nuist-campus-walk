// 食堂点餐：官网“食堂餐厅”点位 → 选窗口、加菜 → 手机支付 → 取餐号、出餐倒计时 → 取餐 → 用餐（饱腹度）。
// 菜单与价格是游戏内容（web/public/data/menus.json），界面底部固定提示。
import { h, ri, yuan } from './ui.js';

export function createCanteen(env) {
  const { S, save, wallet, modal, tgt, tdist, tasks, say } = env;
  let menus = null, open = [], closed = [];

  function setData(m) {
    menus = m;
    open = Object.entries(m.canteens).map(([name, c]) => ({ name, ...c, t: tgt(name) })).filter((c) => c.t);
    closed = Object.entries(m.closed || {}).map(([name, msg]) => ({ name, msg, t: tgt(name) })).filter((c) => c.t);
  }

  function interactable(pos) {
    for (const c of open) {
      if (tdist(c.t, pos.x, pos.z) > 10) continue;
      const want = tasks.wantDish(c.name);
      return { text: `按 E 点餐（${c.name}）${want ? ` · 室友要「${want}」` : ''}`, run: () => menu(c) };
    }
    for (const c of closed) if (tdist(c.t, pos.x, pos.z) < 10) return { text: `${c.name} · 按 E 看看`, run: () => say(c.msg, 3) };
    return null;
  }

  function menu(c) {
    let win = 0, stage = 'menu', err = '', tick = null;
    const cart = new Map(), want = tasks.wantDish(c.name);
    if (want) win = Math.max(0, c.windows.findIndex((w) => w.dishes.some((d) => d[0] === want)));
    const body = h('div', { class: 'ct' });
    const total = () => Math.round([...cart.values()].reduce((s, it) => s + it.price * it.qty, 0) * 100) / 100;
    const add = (d, wi) => { const it = cart.get(d[0]) || { name: d[0], price: d[1], qty: 0, win: wi }; it.qty++; cart.set(d[0], it); err = ''; draw(); };
    const sub = (name) => { const it = cart.get(name); if (it && --it.qty <= 0) cart.delete(name); draw(); };

    function draw() {
      const w = c.windows[win];
      body.replaceChildren(
        h('div', { class: 'lm-head' }, h('b', {}, c.name), h('span', { class: 'lm-tag' }, `余额 ${yuan(S.money)}`),
          h('button', { class: 'lm-x', onclick: () => modal.close(), 'aria-label': '关闭' }, '×')),
        want ? h('p', { class: 'lm-sub' }, `室友要一份「${want}」，买到会自动打包带走。`) : null,
        h('div', { class: 'ct-body' },
          h('div', { class: 'ct-wins' }, c.windows.map((x, i) => h('button', { class: i === win ? 'on' : '', onclick: () => { win = i; draw(); } }, `${x.icon} ${i + 1} 号 ${x.name}`))),
          h('div', { class: 'ct-dishes' }, w.dishes.map((d) => h('button', { class: `ct-dish${d[0] === want ? ' want' : ''}`, onclick: () => add(d, win) },
            h('b', {}, d[0]), h('span', {}, yuan(d[1])), d[2] ? h('em', {}, d[2]) : null, h('i', {}, '+')))),
          h('div', { class: 'ct-cart' }, h('h4', {}, '已点'),
            cart.size ? [...cart.values()].map((it) => h('div', { class: 'ct-line' }, h('span', {}, it.name),
              h('button', { onclick: () => sub(it.name), 'aria-label': '减一份' }, '−'), h('b', {}, `×${it.qty}`), h('span', {}, yuan(it.price * it.qty))))
              : h('p', { class: 'lm-sub' }, '点菜品加入'),
            h('div', { class: 'ct-total' }, '合计 ', h('b', {}, yuan(total()))),
            err ? h('p', { class: 'ct-err' }, err) : null,
            h('button', { class: 'lm-primary', onclick: pay }, '手机支付（Enter）'))),
        h('p', { class: 'lm-note' }, `${menus.note} · 数字键切换窗口 · Esc 离开`));
    }

    function pay() {
      if (stage !== 'menu') return;
      const sum = total();
      if (!cart.size) { err = '还没点菜'; draw(); return; }
      if (!wallet.can(sum)) { err = `余额不足（${yuan(S.money)}），去群里接单挣点钱吧`; draw(); return; }
      wallet.pay(sum, `${c.short} 餐费`);
      stage = 'cook';
      const no = `A${String(ri(1, 199)).padStart(3, '0')}`, items = [...cart.values()], w0 = items[0].win;
      let t = 0, T = 4 + items.length * 1.5, packed = null;
      const bar = h('i'), msg = h('p', { class: 'lm-sub' }, '后厨正在做……');
      const btn = h('button', { class: 'lm-primary', hidden: true, onclick: () => pickup() }, '取餐（E）');
      body.replaceChildren(
        h('div', { class: 'lm-head' }, h('b', {}, `${c.name} · 取餐号`), h('span', { class: 'lm-tag' }, `已付 ${yuan(sum)}`)),
        h('div', { class: 'ct-no' }, no), h('div', { class: 'ct-bar' }, bar), msg,
        h('div', { class: 'ct-items' }, items.map((it) => `${it.name}×${it.qty}`).join('、')), btn,
        h('p', { class: 'lm-note' }, menus.note));
      function pickup() {
        if (stage !== 'ready') return;
        packed = tasks.onFood([...cart.keys()]);
        if (packed) { const it = cart.get(packed); if (--it.qty <= 0) cart.delete(packed); }
        const n = [...cart.values()].reduce((s, it) => s + it.qty, 0);
        if (!n) { modal.close(); say(`已打包「${packed}」，送去给室友吧`, 4); return; }
        stage = 'eat'; t = 0; T = 2.5 + n * 1.5;
        msg.textContent = packed ? `已打包「${packed}」给室友。用餐中……` : '用餐中……';
        btn.hidden = true; bar.style.width = '0%';
      }
      tick = (dt) => {
        t += dt; bar.style.width = `${Math.min(100, t / T * 100)}%`;
        if (stage === 'cook' && t >= T) {
          stage = 'ready'; btn.hidden = false;
          msg.textContent = `出餐啦！请到 ${w0 + 1} 号窗口（${c.windows[w0].name}）取餐`;
        } else if (stage === 'eat' && t >= T) {
          const n = [...cart.values()].reduce((s, it) => s + it.qty, 0);
          S.hunger = Math.min(100, S.hunger + 30 * n); S.stats.meals++; save();
          modal.close();
          say(`吃饱了！饱腹 ${Math.round(S.hunger)}%${packed ? ` · 别忘了把「${packed}」送给室友` : ''}`, 4);
        }
      };
      tick.pickup = pickup;
    }

    draw();
    modal.open(body, {
      wide: true,
      canClose: () => stage === 'menu',
      tick: (dt) => { if (stage !== 'menu' && stage !== 'ready') tick?.(dt); },
      key(e) {
        if (e.code === 'KeyE' || e.code === 'Enter') { if (stage === 'ready') tick.pickup(); else if (stage === 'menu' && e.code === 'Enter') pay(); return true; }
        const d = /^Digit([1-9])$/.exec(e.code);
        if (d && stage === 'menu' && c.windows[d[1] - 1]) { win = d[1] - 1; draw(); return true; }
        return false;
      },
    });
  }

  return { setData, interactable };
}
