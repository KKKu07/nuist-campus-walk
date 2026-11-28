// 任务：群聊 / 私聊发单 → 接单 → 蓝色光柱 + 顶部任务条导航 → 到点按 E（替课点名、取件、交付）→ 转账到账。
// 第一版三种：替课（信大互助群）、取快递（同学·小林）、带饭（室友·阿杰，和食堂点餐联动）。全部是虚构的游戏内容。
import * as THREE from 'three';
import { h, rnd, ri, pick, shuffle, fill, mmss, yuan } from './ui.js';

export function createTasks(env) {
  const { ctx, S, save, wallet, post, modal, tgt, tdist, beaconAt } = env;
  const { P, say } = ctx;
  let data = null, menus = null, offer = null, clock = 0, nextOfferAt = 20, nextChatAt = 45, hudT = 0, saveT = 0;

  // world beacon for the current step
  const beamMat = new THREE.MeshBasicMaterial({ color: '#4aa8ff', transparent: true, opacity: 0.3, depthWrite: false, side: THREE.DoubleSide, fog: false });
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(1.4, 1.4, 80, 16, 1, true).translate(0, 40, 0), beamMat);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(3, 0.25, 8, 40).rotateX(Math.PI / 2), new THREE.MeshBasicMaterial({ color: '#4aa8ff' }));
  beam.visible = ring.visible = false;
  ctx.scene.add(beam, ring);

  // HUD tracker under the 打卡 bar
  const tTitle = h('b'), tStep = h('span', { class: 'lt-step' }), tArrow = h('i', {}, '↑'), tDist = h('span', { class: 'lt-dist' });
  const trk = h('div', { id: 'lifeTask', hidden: true, title: '打开手机任务页', onclick: () => env.openApp('tasks') }, tTitle, tStep, tArrow, tDist);
  document.body.append(trk);

  const step = () => (S.task ? S.task.steps[S.task.step] : null);
  const stepT = () => { const st = step(); return st ? tgt(st.target) : null; };
  const who = (t) => t.poster.split('·').pop();

  function placeBeacon() {
    const T = stepT();
    if (!T) { beam.visible = ring.visible = false; return; }
    const [x, z] = beaconAt(T, P.pos.x, P.pos.z), y = ctx.heightAt(x, z);
    beam.position.set(x, y, z); ring.position.set(x, y + 2.2, z);
    beam.visible = ring.visible = true;
  }
  if (S.task) placeBeacon();

  const nearPick = (list, x, z, lo, hi) => {
    const c = list.filter((t) => { const d = Math.hypot(t.x - x, t.z - z); return d > lo && d < hi; });
    return pick(c.length ? c : list);
  };

  function makeOffer() {
    // which job types are offered: tasks.json 'kinds' (替课 is left out of the teacher-review build)
    const kinds = data.kinds?.length ? data.kinds : ['class', 'express', 'food'];
    const kind = kinds[S.stats.rot++ % kinds.length];
    let o = null;
    if (kind === 'class') {
      const bs = data.classBuildings.map(tgt).filter(Boolean);
      if (!bs.length) return;
      const b = nearPick(bs, P.pos.x, P.pos.z, 150, 1000);
      const [name, decoys] = pick(data.names);
      const room = `${pick(['A', 'B', 'C'])}${ri(1, 5)}${String(ri(1, 18)).padStart(2, '0')}`;
      const course = pick(data.courses), pay = Math.round(rnd(...data.class.reward) / 5) * 5;
      o = { kind, chat: 'group', poster: pick(data.posters), pay, limit: data.class.limit, title: `替课 · ${b.name} ${room}`,
        name, decoys, course, building: b.name, room, text: fill(pick(data.class.texts), { building: b.name, room, course, name, pay }),
        steps: [{ label: `去${b.name} ${room}，替「${name}」上《${course}》`, target: b.name, act: 'class' }] };
    } else if (kind === 'express') {
      const pts = data.express.points.map(tgt).filter(Boolean);
      if (!pts.length || !env.dorms.length) return;
      const p = nearPick(pts, P.pos.x, P.pos.z, 0, 1200), dorm = nearPick(env.dorms, p.x, p.z, 120, 800);
      const code = `${ri(1, 6)}-${ri(1, 4)}-${ri(1000, 9999)}`, pay = ri(...data.express.tip);
      o = { kind, chat: 'classmate', poster: data.people.classmate, pay, limit: data.express.limit, title: `取快递 · ${p.name}`, code, dorm: dorm.name,
        text: fill(pick(data.express.texts), { point: p.name, code, dorm: dorm.name, pay }),
        steps: [{ label: `去${p.name}取快递（取件码 ${code}）`, target: p.name, act: 'pickup' }, { label: `把快递送到${dorm.name}楼下`, target: dorm.name, act: 'deliver' }] };
    } else {
      const names = Object.keys(menus?.canteens || {}).filter((n) => tgt(n));
      if (!names.length || !env.dorms.length) return;
      const cn = pick(names), c = menus.canteens[cn], ct = tgt(cn);
      const dishes = c.windows.flatMap((w) => w.dishes.filter((d) => d[1] >= 6).map((d) => ({ name: d[0], price: d[1] })));
      const dish = pick(dishes), dorm = nearPick(env.dorms, ct.x, ct.z, 120, 800), pay = dish.price + ri(...data.food.tip);
      o = { kind, chat: 'roommate', poster: data.people.roommate, pay, limit: data.food.limit, title: `带饭 · ${dish.name}`, dish: dish.name, canteen: cn, dorm: dorm.name,
        text: fill(pick(data.food.texts), { canteen: c.short, dish: dish.name, dorm: dorm.name, pay }),
        steps: [{ label: `去${c.short}买「${dish.name}」`, target: cn, act: 'buy' }, { label: `把饭送到${dorm.name}楼下`, target: dorm.name, act: 'deliver' }] };
    }
    const m = post(o.chat, o.poster, o.text, {});
    m.offer = o.id = m.id;
    o.expires = clock + 120;
    offer = o;
    save(); env.refresh();
  }

  function endTask() {
    S.task = null; beam.visible = ring.visible = false;
    nextOfferAt = clock + rnd(40, 80);
    save(); env.refresh();
  }
  function complete(pay, msg) {
    const t = S.task;
    post(t.chat, t.poster, msg);
    if (pay > 0) { post(t.chat, t.poster, `[转账] ${yuan(pay)}`, { pay }); wallet.earn(pay, t.title); }
    S.stats[t.kind]++;
    say(pay > 0 ? `完成：${t.title} · 收到 ${yuan(pay)}` : `结束：${t.title}`, 4);
    endTask();
  }
  function fail() {
    const t = S.task;
    post(t.chat, t.poster, t.kind === 'class' ? '人呢？？老师已经点完名了……' : '人呢？算了我自己去吧');
    say(`任务超时：${t.title}`, 4);
    endTask();
  }
  function advance() {
    S.task.step++;
    placeBeacon(); save(); env.refresh();
    say(`下一步：${step().label}`, 4);
  }

  // ---- mini-games ----
  function classGame() {
    const t = S.task;
    const seq = shuffle([t.name, t.name, t.name, ...t.decoys, ...shuffle([...data.others]).slice(0, 3)]);
    if (seq[0] === t.name) seq.push(seq.shift());   // give the player a beat before the first real call
    let i = -1, state = 'intro', gap = 2.4, win = 0, cur = '', answered = false, hits = 0, misses = 0, wrongs = 0, result = null;
    const teacher = h('div', { class: 'cls-teacher' }, '老师：上课了，先点个名……');
    const fb = h('div', { class: 'cls-fb' });
    const score = h('span');
    const btn = h('button', { class: 'lm-primary', onclick: () => answer() }, '到！（E）');
    const upd = () => { score.textContent = `答到 ${hits}/3 · 失误 ${misses + wrongs}`; };
    const note = (text, cls = '') => { fb.textContent = text; fb.className = `cls-fb ${cls}`; };
    upd();
    function answer() {
      if (state === 'done') { modal.close(); settle(); return; }
      if (state !== 'call' || answered) return;
      answered = true;
      if (cur === t.name) { hits++; note('✓ “到！” 老师低头打了个勾', 'good'); } else { wrongs++; note(`全班都回头看你……老师喊的是「${cur}」`, 'bad'); }
      upd();
    }
    function finish() {
      state = 'done';
      const err = misses + wrongs, pay = err === 0 ? t.pay : err === 1 ? Math.round(t.pay * 0.6) : 0;
      result = { pay, err };
      teacher.textContent = '老师：好，今天就讲到这里，下课！';
      note(err === 0 ? '完美替课，没人发现。' : err === 1 ? '老师好像有点起疑……' : `老师：“你不是${t.name}吧？” 替课被抓了。`, err === 0 ? 'good' : 'bad');
      btn.textContent = '离开教室（E）';
    }
    function settle() {
      if (result.pay > 0) complete(result.pay, result.err === 0 ? '稳！钱转你了' : '听说老师差点发现……少给点哈');
      else { post(t.chat, t.poster, '被抓了？！完了完了……钱就不给了'); say('替课被老师发现，没拿到钱', 4); endTask(); }
    }
    const body = h('div', { class: 'cls' },
      h('div', { class: 'lm-head' }, h('b', {}, `${t.building} ${t.room} ·《${t.course}》`), h('span', { class: 'lm-tag' }, '游戏内容')),
      h('p', { class: 'lm-sub' }, `你在替「${t.name}」上课。老师点到「${t.name}」时按 E 或点“到！”；点别人（名字再像也不是）别出声。`),
      h('div', { class: 'cls-board' }, teacher, fb),
      h('div', { class: 'lm-foot' }, score, btn));
    modal.open(body, {
      pauseTask: true, canClose: false,
      tick(dt) {
        if (state === 'call') {
          win -= dt;
          if (win <= 0) {
            if (cur === t.name && !answered) { misses++; note(`老师：“${t.name}没来？记旷课！”`, 'bad'); upd(); }
            state = 'gap'; gap = rnd(0.6, 1.2); teacher.textContent = '老师：……';
          }
        } else if (state === 'gap' || state === 'intro') {
          gap -= dt;
          if (gap <= 0) {
            i++;
            if (i >= seq.length) finish();
            else { cur = seq[i]; answered = false; win = 1.8; state = 'call'; teacher.textContent = `老师：${cur}！`; note(''); }
          }
        }
      },
      key(e) { if (['KeyE', 'Space', 'Enter'].includes(e.code)) { if (!e.repeat) answer(); return true; } return false; },
    });
  }

  function parcelGame() {
    const t = S.task, [a, b, c] = t.code.split('-');
    const swap = (s) => { const d = s.split(''); const k = ri(0, d.length - 2); [d[k], d[k + 1]] = [d[k + 1], d[k]]; return d.join(''); };
    const decoys = new Set();
    for (let n = 0; decoys.size < 5 && n < 50; n++) {
      const v = pick([`${a}-${b}-${swap(c)}`, `${a}-${ri(1, 4)}-${c}`, `${ri(1, 6)}-${b}-${c}`, `${a}-${b}-${ri(1000, 9999)}`]);
      if (v !== t.code) decoys.add(v);
    }
    const codes = shuffle([t.code, ...decoys]);
    const fb = h('p', { class: 'lm-sub' }, '在货架上找到和取件码一样的包裹（点它，或按数字键）。');
    const choose = (code, el) => {
      if (code === t.code) { modal.close(); say(`取到快递了，送去${t.dorm}楼下`, 4); advance(); return; }
      el.classList.remove('shake'); void el.offsetWidth; el.classList.add('shake');
      fb.textContent = `不是这个（${code}），再对一下取件码 ${t.code}`;
    };
    const grid = h('div', { class: 'pc-grid' }, codes.map((code, k) => h('button', { class: 'pc-box', onclick: (e) => choose(code, e.currentTarget) }, h('i', {}, String(k + 1)), h('b', {}, code))));
    modal.open(h('div', { class: 'pc' },
      h('div', { class: 'lm-head' }, h('b', {}, `${step().target} · 取件码 ${t.code}`), h('button', { class: 'lm-x', onclick: () => modal.close(), 'aria-label': '关闭' }, '×')),
      fb, grid), {
      pauseTask: true,
      key(e) { const d = /^Digit([1-6])$/.exec(e.code); if (d && codes[d[1] - 1]) { choose(codes[d[1] - 1], grid.children[d[1] - 1]); return true; } return false; },
    });
  }

  function drawTracker() {
    const t = S.task, T = stepT();
    if (!t || !T) { trk.hidden = true; return; }
    trk.hidden = false;
    const d = tdist(T, P.pos.x, P.pos.z);
    const ang = Math.atan2(-(beam.position.x - P.pos.x), -(beam.position.z - P.pos.z)) - P.yaw;
    tTitle.textContent = t.title;
    tStep.textContent = step().label;
    tArrow.style.transform = `rotate(${-ang}rad)`;
    tDist.textContent = `${d > 1000 ? (d / 1000).toFixed(1) + ' km' : Math.round(d) + ' m'} · ${mmss(t.left)}`;
    trk.classList.toggle('hurry', t.left < 45);
  }

  return {
    get offer() { return offer; },
    get kinds() { return data?.kinds?.length ? data.kinds : ['class', 'express', 'food']; },
    setData(d, m) { data = d; menus = m; },
    // quiet: the guided route is running, so no new job offers or group chatter
    update(dt, paused, quiet) {
      clock += dt;
      if (quiet) { nextOfferAt = Math.max(nextOfferAt, clock + 20); nextChatAt = Math.max(nextChatAt, clock + 30); }
      if (data && !S.task && !offer && clock > nextOfferAt) makeOffer();
      if (offer && clock > offer.expires) {
        post(offer.chat, offer.poster, offer.kind === 'class' ? '有人接了，谢谢大家' : '算了不用了，我自己去', { quiet: true });
        offer = null; nextOfferAt = clock + 30; env.refresh();
      }
      if (data && clock > nextChatAt) { post('group', pick(data.posters), pick(data.chatter), { quiet: true }); nextChatAt = clock + rnd(45, 90); }
      if (S.task && !paused) {
        S.task.left -= dt;
        if (S.task.left <= 0) fail();
        else if ((saveT += dt) > 3) { saveT = 0; save(); }
      }
      if (ring.visible) { ring.rotation.y = clock; ring.position.y = beam.position.y + 2.2 + Math.sin(clock * 2) * 0.3; }
      if ((hudT -= dt) <= 0) { hudT = 0.2; drawTracker(); }
    },
    interactable() {
      const t = S.task, st = step();
      if (!data || !t || !st || st.act === 'buy') return null;
      const T = tgt(st.target);
      if (!T || tdist(T, P.pos.x, P.pos.z) > 10) return null;
      if (st.act === 'class') return { text: `按 E 进教室替课（${t.building} ${t.room}）`, run: classGame };
      if (st.act === 'pickup') return { text: `按 E 取快递（取件码 ${t.code}）`, run: parcelGame };
      return { text: `按 E 把${t.kind === 'food' ? '饭' : '快递'}交给${who(t)}`, run: () => complete(t.pay, t.kind === 'food' ? '香！谢啦，钱转你了' : '收到！谢谢～') };
    },
    accept(id) {
      if (!offer || offer.id !== id) return;
      if (S.task) { say('先完成手上的任务', 2); return; }
      const o = offer;
      offer = null;
      S.task = { ...o, step: 0, left: o.limit };
      delete S.task.expires;
      post(o.chat, 'me', '我来！');
      post(o.chat, o.poster, o.kind === 'class' ? `好嘞！记住，老师点「${o.name}」你就喊“到”` : '太好了，靠你了！', { quiet: true });
      placeBeacon(); save(); env.refresh();
      say(`已接单：${o.steps[0].label}（限时 ${mmss(o.limit)}）`, 4);
    },
    decline(id) {
      if (!offer || offer.id !== id) return;
      post(offer.chat, 'me', '这单我去不了');
      offer = null; nextOfferAt = clock + 40; env.refresh();
    },
    abandon(reason) {
      const t = S.task;
      if (!t) return;
      post(t.chat, 'me', reason === 'travel' ? '临时有事去不了了，抱歉！' : '不好意思，这单我放弃了');
      say('任务已放弃', 2);
      endTask();
    },
    wantDish(canteen) { const st = step(); return S.task?.kind === 'food' && st?.act === 'buy' && S.task.canteen === canteen ? S.task.dish : null; },
    onFood(names) {
      const st = step();
      if (S.task?.kind !== 'food' || st?.act !== 'buy' || !names.includes(S.task.dish)) return null;
      const d = S.task.dish;
      advance();
      return d;
    },
    reset() { offer = null; beam.visible = ring.visible = false; nextOfferAt = clock + 20; trk.hidden = true; },
  };
}
