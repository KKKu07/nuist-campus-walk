const one = selector => document.querySelector(selector);
const arrivalMetres = 3.5;
const directions = ['前方', '右前方', '右侧', '右后方', '后方', '左后方', '左侧', '左前方'];

function label(node, value) {
  if (node.textContent !== value) node.textContent = value;
}

function distanceLabel(metres) {
  return metres >= 1000 ? (metres / 1000).toFixed(1) + ' 公里' : Math.round(metres) + ' 米';
}

export function campusHud({places, save, distance, changeMap, focusPlace, jump, riding, read, photo}) {
  const search = one('#placeSearch'), list = one('#placeList'), guide = one('#walkingGuide');
  const task = one('#task'), hint = one('#taskHint'), taskButton = one('#trackTask');
  const taskDistance = one('#taskDistance'), interact = one('#interact'), interactName = interact.querySelector('strong');
  const guideName = guide.querySelector('strong'), guideText = guide.querySelector('span'), compass = guide.querySelector('i');
  const close = one('#closeMap'), detail = one('#placeDetail'), empty = one('#emptyPlaces');
  const progress = one('#progress'), notice = one('#notice'), guideButton = guide.querySelector('button');
  const pin = one('#selectedPin');
  const filters = [...document.querySelectorAll('[data-filter]')];
  let target = null, selected = null, taskPlace = null, taskAction = '', nearest = null;
  let filter = 'all', matches = [], rows = [], toastTimer = 0, nextDistanceUpdate = 0;

  function toast(message) {
    clearTimeout(toastTimer);
    notice.textContent = message;
    toastTimer = setTimeout(() => { notice.textContent = ''; }, 2800);
  }

  function track(place) {
    target = place;
    guideName.textContent = place.short;
    guide.hidden = false;
  }

  guideButton.onclick = () => { target = null; guide.hidden = true; };

  function updateProgress() {
    label(progress, '足迹 ' + save.visited.length + ' / ' + places.length + '　·　留影 ' + save.photos.length);
    const readLibrary = save.read.includes('library');
    taskAction = !readLibrary ? 'read' : !save.photos.includes('yard') ? 'photo' : 'explore';
    taskPlace = places.find(p => p.id === (taskAction === 'read' ? 'library' : 'yard'));
    if (taskAction === 'explore') taskPlace = null;
    label(task, taskAction === 'read' ? '去图书馆读第一篇手记' : taskAction === 'photo' ? '给风云剧场留张影' : '发现下一个校园地标');
    label(hint, taskAction === 'read' ? '走近入口的金色标记，打开图书馆简介。' : taskAction === 'photo' ? '走到剧场入口附近，拍一张校园留影。' : '地图里可以查找还没读过简介的地点。');
  }

  taskButton.onclick = () => {
    if (!taskPlace) { filter = 'unread'; changeMap(true); return; }
    if (nearest === taskPlace) { if (taskAction === 'read') read(); else photo(); }
    else if (target === taskPlace) guideButton.click();
    else track(taskPlace);
  };

  function detailFor(place, focus = false) {
    selected = place;
    detail.hidden = !place;
    if (!place) pin.hidden = true;
    if (place) {
      label(one('#placeName'), place.name);
      label(pin, place.short);
      label(one('#placeStatus'), (save.read.includes(place.id) ? '已读简介' : '未读简介') + '　·　' + distanceLabel(distance(place)));
      one('#jumpTo').disabled = riding();
      if (focus) focusPlace(place);
    }
    for (const row of rows) row.button.setAttribute('aria-pressed', String(row.place === place));
  }

  function renderList() {
    const query = search.value.trim().toLocaleLowerCase();
    matches = places.filter(p => (filter === 'all' || !save.read.includes(p.id)) &&
      (p.name + p.short + (p.id === 'research' ? '信息科技大楼' : p.id === 'clock' ? '逸夫楼' : '')).toLocaleLowerCase().includes(query))
      .sort((a,b) => distance(a) - distance(b));
    for (const button of filters) button.setAttribute('aria-pressed', String(button.dataset.filter === filter));
    rows = matches.map(place => {
      const item = document.createElement('li'), button = document.createElement('button');
      const name = document.createElement('strong'), metres = document.createElement('small');
      name.textContent = place.short;
      metres.textContent = distanceLabel(distance(place));
      button.onclick = () => detailFor(place, true);
      button.append(name, metres); item.append(button);
      return {item, button, place, metres};
    });
    list.replaceChildren(...rows.map(row => row.item));
    empty.hidden = rows.length > 0;
    if (!empty.hidden) empty.textContent = query ? '没有找到这个地点，试试简称或清空搜索。' : '所有地点的简介都读过了。';
    detailFor(matches.includes(selected) ? selected : matches[0]);
  }

  filters.forEach(button => { button.onclick = () => { filter = button.dataset.filter; renderList(); }; });
  search.oninput = renderList;
  one('#walkTo').onclick = () => { if (selected) { track(selected); changeMap(false); } };
  one('#jumpTo').onclick = () => {
    if (!selected || riding()) return;
    jump(selected);
    target = null;
    toast('已到达' + selected.short);
    changeMap(false);
  };
  close.onclick = () => changeMap(false);

  function mapOpened(open) {
    one('#destinations').hidden = !open;
    pin.hidden = true;
    document.body.classList.toggle('in-atlas', open);
    if (open) {
      selected = target || nearest;
      search.value = ''; renderList(); close.focus({preventScroll:true});
    } else {
      filter = 'all';
      one('#map').focus({preventScroll:true});
    }
  }

  function update({x, z, yaw, started, overview, now}) {
    nearest = null;
    let best = arrivalMetres;
    if (started && !overview && !riding()) {
      for (const place of places) {
        const metres = distance(place);
        if (metres <= best) { best = metres; nearest = place; }
      }
    }
    interact.hidden = !nearest;
    if (nearest) label(interactName, nearest.short);
    if (overview && now >= nextDistanceUpdate) {
      nextDistanceUpdate = now + 450;
      for (const row of rows) label(row.metres, distanceLabel(distance(row.place)));
      detailFor(selected);
    }
    if (started && !overview) {
      label(taskDistance, taskPlace ? distanceLabel(distance(taskPlace)) : '');
      label(taskButton, !taskPlace ? '查看未读地点' : nearest === taskPlace ? (taskAction === 'read' ? '阅读简介' : '拍照留影') : target === taskPlace ? '结束指引' : '指引我前往');
    }
    guide.hidden = !target || !started || overview;
    if (!guide.hidden) {
      if (nearest === target) {
        toast('已到达' + target.short);
        target = null; guide.hidden = true;
      } else {
        const dx = target.entry.x - x, dz = target.entry.z - z;
        const angle = Math.atan2(dx * Math.cos(yaw) - dz * Math.sin(yaw), -dx * Math.sin(yaw) - dz * Math.cos(yaw));
        const direction = directions[(Math.round(angle / (Math.PI / 4)) + 8) % 8];
        compass.style.transform = 'rotate(' + Math.round(angle * 180 / Math.PI) + 'deg)';
        label(guideText, direction + '　·　直线 ' + distanceLabel(distance(target)));
      }
    }
    return nearest;
  }

  function positionPin(point) {
    const visible = selected && Math.abs(point.x) < .97 && Math.abs(point.y) < .95 && Math.abs(point.z) <= 1;
    pin.hidden = !visible;
    if (visible) {
      pin.style.left = ((point.x + 1) * 50).toFixed(2) + '%';
      pin.style.top = ((1 - point.y) * 50).toFixed(2) + '%';
    }
  }

  updateProgress();
  return {update, updateProgress, mapOpened, positionPin, toast, get selected() { return selected; }, get target() { return target; }};
}
