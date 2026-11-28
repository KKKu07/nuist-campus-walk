// 钱包：游戏内余额（元），收支账单最近 50 条。
export function createWallet(S, save, onChange) {
  const add = (amount, title) => {
    S.money = Math.round((S.money + amount) * 100) / 100;
    S.txns.unshift({ t: Date.now(), amount, title });
    if (S.txns.length > 50) S.txns.length = 50;
    save(); onChange();
  };
  return {
    get balance() { return S.money; },
    can(a) { return S.money >= a - 1e-9; },
    // force: allow going below zero (7ma overtime is billed even if the balance runs out)
    pay(a, title, force = false) { if (!force && !this.can(a)) return false; add(-a, title); return true; },
    earn(a, title) { S.stats.earned = Math.round((S.stats.earned + a) * 100) / 100; add(a, title); },
  };
}
