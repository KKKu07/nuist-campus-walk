// 存档：localStorage 'nuist-life-v1'（余额、账单、聊天、任务、统计）。照片在 camera.js 的 IndexedDB。
const KEY = 'nuist-life-v1';

export const freshState = () => ({
  v: 1, money: 50, hunger: 80, txns: [], chats: {}, unread: {}, task: null, intro: false,
  stats: { class: 0, express: 0, food: 0, meals: 0, earned: 0, rides: 0, rot: 0 }, seq: 1,
});

export function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (s && s.v === 1) { const f = freshState(); return { ...f, ...s, stats: { ...f.stats, ...s.stats } }; }
  } catch { /* corrupt or private mode */ }
  return freshState();
}

// written synchronously: the state is small, saves only happen on events (and every few seconds),
// and a debounced timer can be throttled in background tabs and lost on reload
export function saveState(s) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* quota / private */ }
}
