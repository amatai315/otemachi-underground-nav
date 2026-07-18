// 自前実装のダイクストラ法。graph.json の nodes/edges をそのままグラフとして使う。

/**
 * @param {{nodes: Array<{id:string,x:number,y:number,z:number,floorOrdinal:number}>, edges: Array<{from:string,to:string,weight:number}>}} graph
 * @param {string} startId
 * @param {string} goalId
 * @returns {Array<{id:string,x:number,y:number,z:number,floorOrdinal:number}>|null} 経路上のノード列(座標付き)。到達不可なら null
 */
export function findShortestPath(graph, startId, goalId) {
  const nodesById = new Map(graph.nodes.map((n) => [n.id, n]));
  if (!nodesById.has(startId) || !nodesById.has(goalId)) return null;

  const adjacency = new Map();
  for (const n of graph.nodes) adjacency.set(n.id, []);
  for (const e of graph.edges) {
    adjacency.get(e.from)?.push({ to: e.to, weight: e.weight });
    adjacency.get(e.to)?.push({ to: e.from, weight: e.weight });
  }

  const dist = new Map();
  const prev = new Map();
  const visited = new Set();
  for (const id of nodesById.keys()) dist.set(id, Infinity);
  dist.set(startId, 0);

  // 単純な線形探索の優先度キュー(このPoCの規模ではノード数が小さいため十分)
  while (true) {
    let currentId = null;
    let currentDist = Infinity;
    for (const [id, d] of dist) {
      if (!visited.has(id) && d < currentDist) {
        currentDist = d;
        currentId = id;
      }
    }
    if (currentId === null) break;
    if (currentId === goalId) break;
    visited.add(currentId);

    for (const { to, weight } of adjacency.get(currentId) ?? []) {
      if (visited.has(to)) continue;
      const alt = currentDist + weight;
      if (alt < dist.get(to)) {
        dist.set(to, alt);
        prev.set(to, currentId);
      }
    }
  }

  if (dist.get(goalId) === Infinity || dist.get(goalId) === undefined) return null;

  const pathIds = [goalId];
  let cur = goalId;
  while (cur !== startId) {
    const p = prev.get(cur);
    if (p === undefined) return null;
    pathIds.push(p);
    cur = p;
  }
  pathIds.reverse();

  return pathIds.map((id) => nodesById.get(id));
}
