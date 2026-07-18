import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const FLOOR_DEPTH = 3.0; // 押し出し高さ(m)。床から天井方向への厚み

// toll値の意味は出典データに凡例が無いため、フィールドの値の分布から
// 「1=改札内寄り(有料側)」「それ以外=無料の公共通路」という簡易分類にとどめる。
// 背景(ほぼ黒)とはっきり区別できるよう、明度の高い色を選ぶ。
const TOLL_COLOR = {
  '1': 0x5b8def, // 改札内側(有料エリア)寄り: 鮮やかな青
  default: 0xd8dee6, // 無料の通路・空間: 明るいグレー
};

export function initScene(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x10141a);

  const camera = new THREE.PerspectiveCamera(
    55,
    container.clientWidth / container.clientHeight,
    0.1,
    2000
  );
  camera.position.set(60, 90, 140);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const dir = new THREE.DirectionalLight(0xffffff, 0.7);
  dir.position.set(80, 150, 60);
  scene.add(dir);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x1a1a2e, 0.5));

  // 見下ろし(俯瞰)の煽り角(polar angle)は初期値に固定したまま、左右の回転(azimuth)と
  // 平行移動(パン)の両方を有効にする。煽り角だけを固定することで、横から覗き込むような
  // 角度にはならず、常に見下ろし視点を保ったまま視点を回せる。
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, -4, 0);
  controls.update();
  const fixedPolarAngle = controls.getPolarAngle();
  controls.minPolarAngle = fixedPolarAngle;
  controls.maxPolarAngle = fixedPolarAngle;
  controls.enableRotate = true; // 左右回転(煽り角は固定なので実質は水平方向のみ)
  controls.enablePan = true; // ドラッグで平行移動
  controls.enableZoom = true; // ホイール/ピンチでズーム
  controls.screenSpacePanning = true;
  // タッチ: 1本指=回転、2本指=ズーム+パン。マウス: 左=回転、右=パン(three.jsデフォルト)。
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
  controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
  controls.minDistance = 20;
  controls.maxDistance = 500;
  controls.update();

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  window.addEventListener('resize', resize);
  window.addEventListener('orientationchange', resize);

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  return { scene, camera, renderer, controls };
}

// GeoJSON のリング([[x,y], ...])から THREE.Shape / Path を作る
function ringToPoints(ring) {
  return ring.map(([x, y]) => new THREE.Vector2(x, y));
}

function polygonToShape(coordinates) {
  const [outer, ...holes] = coordinates;
  const shape = new THREE.Shape(ringToPoints(outer));
  for (const hole of holes) {
    shape.holes.push(new THREE.Path(ringToPoints(hole)));
  }
  return shape;
}

/**
 * floors.geojson の各フィーチャーを押し出しポリゴンとしてシーンに追加する。
 * 座標変換: GeoJSON (x, y) [投影後のローカルメートル] を Shape の(x,y)平面としてExtrudeし、
 * rotateX(-90°) で world (x, y=押し出し高さ, z=-y) に倒す。これは graph.json のノード座標
 * (x, y=ordinal*4, z=-y) と同じ変換規則になる(北が奥/-Z、南が手前/+Z)。
 */
export function buildFloors(scene, floorsGeojson) {
  const group = new THREE.Group();

  for (const feature of floorsGeojson.features) {
    const { geometry, properties } = feature;
    const polygons =
      geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;

    const color = TOLL_COLOR[properties.toll] ?? TOLL_COLOR.default;
    const material = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.9,
      metalness: 0.0,
      side: THREE.DoubleSide,
    });

    for (const coords of polygons) {
      let shape;
      try {
        shape = polygonToShape(coords);
      } catch {
        continue;
      }
      const geom = new THREE.ExtrudeGeometry(shape, {
        depth: FLOOR_DEPTH,
        bevelEnabled: false,
      });
      geom.rotateX(-Math.PI / 2);

      const mesh = new THREE.Mesh(geom, material);
      mesh.position.y = properties.floorOrdinal * 4.0;
      group.add(mesh);
    }
  }

  scene.add(group);
  return group;
}

// 経路ハイライトの高さオフセット。各フロアの押し出しブロック(天井=FLOOR_DEPTH)より
// 上に浮かせて描画することで、ブロック内部に埋もれて見えなくなるのを防ぐ。
const PATH_Y_OFFSET = FLOOR_DEPTH + 0.6;

let pathLine = null;
let pathMarkers = null;
let pathMaterials = []; // highlightPath() で生成したMaterial群。clearPath()でdisposeする

/**
 * ダイクストラで得た経路(ノード列)をチューブ状のラインと始点/終点マーカーで描画する。
 * ノードの x,y,z を全て辿るため、階段等での上下移動が視覚的にわかる。
 * フロアの押し出しブロックより高い位置に浮かせ、depthTest を切って常に手前に
 * 描画することで、床ブロックに埋もれて見えなくなる問題を避ける。
 */
export function highlightPath(scene, pathNodes) {
  clearPath(scene);
  if (!pathNodes || pathNodes.length < 2) return;

  const points = pathNodes.map((n) => new THREE.Vector3(n.x, n.y + PATH_Y_OFFSET, n.z));

  const curvePath = new THREE.CurvePath();
  for (let i = 0; i < points.length - 1; i++) {
    curvePath.add(new THREE.LineCurve3(points[i], points[i + 1]));
  }
  const tubularSegments = Math.max(points.length * 2, 8);
  const geometry = new THREE.TubeGeometry(curvePath, tubularSegments, 0.45, 8, false);
  const material = new THREE.MeshBasicMaterial({ color: 0xff7a1a, depthTest: false });
  pathLine = new THREE.Mesh(geometry, material);
  pathLine.renderOrder = 999;
  scene.add(pathLine);

  const markerGeom = new THREE.SphereGeometry(1.1, 16, 16);
  pathMarkers = new THREE.Group();
  const startMat = new THREE.MeshBasicMaterial({ color: 0x35d07f, depthTest: false });
  const goalMat = new THREE.MeshBasicMaterial({ color: 0xff3b3b, depthTest: false });

  [
    { point: points[0], material: startMat },
    { point: points[points.length - 1], material: goalMat },
  ].forEach(({ point, material: mat }) => {
    const sphere = new THREE.Mesh(markerGeom, mat);
    sphere.position.copy(point);
    sphere.renderOrder = 999;
    pathMarkers.add(sphere);
  });
  scene.add(pathMarkers);

  pathMaterials = [material, startMat, goalMat];
}

export function clearPath(scene) {
  if (pathLine) {
    scene.remove(pathLine);
    pathLine.geometry.dispose();
    pathLine = null;
  }
  if (pathMarkers) {
    scene.remove(pathMarkers);
    pathMarkers.children.forEach((c) => c.geometry.dispose());
    pathMarkers = null;
  }
  pathMaterials.forEach((m) => m.dispose());
  pathMaterials = [];
}
