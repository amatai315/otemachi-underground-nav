// 出発地/目的地選択UI(タップ選択式)と経路探索ボタンの配線

function floorLabel(ordinal) {
  if (ordinal < 0) return `地下${Math.abs(ordinal)}階 (B${Math.abs(ordinal)}F)`;
  if (ordinal === 0) return `地上 (0F)`;
  return `地上${ordinal}階 (${ordinal}F)`;
}

function groupByFloor(pois) {
  const groups = new Map();
  for (const poi of pois) {
    if (!groups.has(poi.floorOrdinal)) groups.set(poi.floorOrdinal, []);
    groups.get(poi.floorOrdinal).push(poi);
  }
  // 地下から地上へ順に並べる
  return [...groups.entries()].sort((a, b) => a[0] - b[0]);
}

export function setupUI({ pois, onRouteRequest }) {
  const btnStart = document.getElementById('btn-start');
  const btnGoal = document.getElementById('btn-goal');
  const btnRoute = document.getElementById('btn-route');
  const statusEl = document.getElementById('status');

  const picker = document.getElementById('picker');
  const pickerTitle = document.getElementById('picker-title');
  const pickerList = document.getElementById('picker-list');
  const pickerClose = document.getElementById('picker-close');

  const state = { start: null, goal: null };
  let activeTarget = null; // 'start' | 'goal'

  const grouped = groupByFloor(pois);

  function renderList() {
    pickerList.innerHTML = '';
    for (const [ordinal, items] of grouped) {
      const heading = document.createElement('div');
      heading.className = 'floor-heading';
      heading.textContent = floorLabel(ordinal);
      pickerList.appendChild(heading);

      for (const poi of items) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'poi-btn';
        btn.textContent = poi.name;
        btn.addEventListener('click', () => {
          if (activeTarget === 'start') {
            state.start = poi;
            btnStart.textContent = poi.name;
            btnStart.classList.add('chosen');
          } else {
            state.goal = poi;
            btnGoal.textContent = poi.name;
            btnGoal.classList.add('chosen');
          }
          closePicker();
          updateRouteButton();
        });
        pickerList.appendChild(btn);
      }
    }
  }

  function openPicker(target) {
    activeTarget = target;
    pickerTitle.textContent = target === 'start' ? '出発地を選択' : '目的地を選択';
    picker.classList.remove('hidden');
  }

  function closePicker() {
    picker.classList.add('hidden');
    activeTarget = null;
  }

  function updateRouteButton() {
    btnRoute.disabled = !(state.start && state.goal);
  }

  function setStatus(msg) {
    statusEl.textContent = msg ?? '';
  }

  renderList();

  btnStart.addEventListener('click', () => openPicker('start'));
  btnGoal.addEventListener('click', () => openPicker('goal'));
  pickerClose.addEventListener('click', closePicker);

  btnRoute.addEventListener('click', () => {
    if (!state.start || !state.goal) return;
    if (state.start.nodeId === state.goal.nodeId) {
      setStatus('出発地と目的地が同じです');
      return;
    }
    setStatus('');
    onRouteRequest(state.start, state.goal, setStatus);
  });

  return { setStatus };
}
