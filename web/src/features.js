// 玩法总开关：老师检查前要关掉的功能集中在这里，改一个值、重新构建即可。
// 也可以不改代码、在网址后面加参数临时开关：?stunt=0 关飙车翘头，?stunt=1 开。
export const FEATURES = {
  // 骑 7ma / 自行车时 Shift 飙车、按住空格翘头（含加速、压弯、光带、电机声）。关闭：改成 false
  stunts: true,
};
// 另一个已关的项目：手机兼职“替课”单，在 web/public/data/tasks.json 的 "kinds" 里加回 "class" 才会出现。

const q = new URLSearchParams(location.search);
export const stuntsOn = q.has('stunt') ? q.get('stunt') !== '0' : FEATURES.stunts;
