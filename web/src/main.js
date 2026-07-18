import './style.css';
import graphData from './data/graph.json';
import poisData from './data/pois.json';
import floorsRaw from './data/floors.geojson?raw';
import { initScene, buildFloors, highlightPath } from './scene.js';
import { findShortestPath } from './routing.js';
import { setupUI } from './ui.js';

const floorsData = JSON.parse(floorsRaw);

const viewport = document.getElementById('viewport');
const { scene } = initScene(viewport);
buildFloors(scene, floorsData);

setupUI({
  pois: poisData,
  onRouteRequest: (start, goal, setStatus) => {
    const path = findShortestPath(graphData, start.nodeId, goal.nodeId);
    if (!path) {
      setStatus('経路が見つかりませんでした');
      return;
    }
    highlightPath(scene, path);
    setStatus(`${path.length}ノードを経由する経路を表示しました`);
  },
});
