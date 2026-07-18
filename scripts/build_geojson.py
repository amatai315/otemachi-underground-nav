"""
Otemachi underground nav - data pipeline.

Shapefile(EPSG:6668, JGD2011 geographic) -> web/src/data/{floors.geojson, graph.json, pois.json}

Source: 2020 "Tokyo Station area indoor map open data" (MLIT / G-Spatial Information Center).
See docs/plans/plan_20260718131125.md for the full design rationale.

Run manually (not part of the Vite build):
    PYTHONIOENCODING=utf-8 python scripts/build_geojson.py
"""
import glob
import math
import os
from collections import defaultdict

import geopandas as gpd
from pyproj import Transformer
from shapely.affinity import translate as shapely_translate
from shapely.geometry import mapping
import json

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
EXTRACTED_ROOT = os.path.join(
    PROJECT_ROOT, "raw-data", "extracted", "東京駅周辺屋内地図オープンデータ（Shapefile）"
)
NW_DIR = os.path.join(EXTRACTED_ROOT, "nw")
OUT_DIR = os.path.join(PROJECT_ROOT, "web", "src", "data")
REF_OPENING_SHP = os.path.join(
    EXTRACTED_ROOT, "2.地下鉄_公共通路", "B1", "ChiyodaOtemati_B1_Opening.shp"
)

RADIUS_M = 450.0
FLOOR_HEIGHT_M = 4.0
POI_SNAP_M = 25.0
SRC_CRS = "EPSG:6668"
PROJ_CRS = "EPSG:6677"

REPORT_PATH = os.path.join(SCRIPT_DIR, "build_report.txt")
report_lines = []


def log(msg):
    report_lines.append(msg)


def sanitize_nan(obj, stats):
    """再帰的にNaN/Infinityのfloatをnullへ変換する(標準JSONは両者を許容しないため)。"""
    if isinstance(obj, dict):
        return {k: sanitize_nan(v, stats) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_nan(v, stats) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        stats["count"] += 1
        return None
    return obj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def haversine_m(lon1, lat1, lon2, lat2):
    """Spherical (haversine) distance in meters between two lon/lat points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def find_space_shapefiles():
    """All *_Space.shp files under the extracted root, excluding nw/."""
    pattern = os.path.join(EXTRACTED_ROOT, "**", "*_Space.shp")
    paths = glob.glob(pattern, recursive=True)
    return [p for p in paths if os.path.normpath(NW_DIR) not in os.path.normpath(p)]


def prefix_for(space_shp_path):
    """'.../ChiyodaOtemati_B1_Space.shp' -> ('.../dir', 'ChiyodaOtemati_B1')"""
    d = os.path.dirname(space_shp_path)
    base = os.path.basename(space_shp_path)
    prefix = base[: -len("_Space.shp")]
    return d, prefix


def translate_geom(geom, dx, dy):
    return shapely_translate(geom, xoff=dx, yoff=dy)


def geom_to_geojson(geom):
    return mapping(geom)


def load_floor_ordinal_map(dir_path, prefix):
    """id -> ordinal, from '<prefix>_Floor.shp' in dir_path. Empty dict if missing."""
    floor_shp = os.path.join(dir_path, f"{prefix}_Floor.shp")
    if not os.path.exists(floor_shp):
        return {}
    floor_gdf = gpd.read_file(floor_shp, encoding="utf-8")
    return dict(zip(floor_gdf["id"], floor_gdf["ordinal"]))


# ---------------------------------------------------------------------------
# 1. Reference point (Otemachi Chiyoda-line ticket gate centroid average)
# ---------------------------------------------------------------------------
opening_ref_gdf = gpd.read_file(REF_OPENING_SHP, encoding="utf-8")
ref_centroids = opening_ref_gdf.geometry.centroid
ref_lon = float(ref_centroids.x.mean())
ref_lat = float(ref_centroids.y.mean())

to_proj = Transformer.from_crs(SRC_CRS, PROJ_CRS, always_xy=True)
ref_x, ref_y = to_proj.transform(ref_lon, ref_lat)

log(f"reference point (lon,lat) = ({ref_lon:.6f}, {ref_lat:.6f})")
log(f"reference point ({PROJ_CRS} local origin) = ({ref_x:.2f}, {ref_y:.2f})")

# ---------------------------------------------------------------------------
# 2. Walking network: nodes + edges within 450m, largest connected component
# ---------------------------------------------------------------------------
nodes_gdf = gpd.read_file(os.path.join(NW_DIR, "Tokyo_node.shp"), encoding="utf-8")
links_gdf = gpd.read_file(os.path.join(NW_DIR, "Tokyo_Link.shp"), encoding="utf-8")

nodes_gdf["dist_ref_m"] = nodes_gdf.geometry.apply(
    lambda g: haversine_m(g.x, g.y, ref_lon, ref_lat)
)
in_range_mask = nodes_gdf["dist_ref_m"] <= RADIUS_M
in_range_ids = set(nodes_gdf.loc[in_range_mask, "node_id"])

log(f"nodes total = {len(nodes_gdf)}, within {RADIUS_M:.0f}m = {len(in_range_ids)}")

edges_in_range = [
    (r.start_id, r.end_id, float(r.distance))
    for r in links_gdf.itertuples()
    if r.start_id in in_range_ids and r.end_id in in_range_ids
]
log(f"edges total = {len(links_gdf)}, within range (both endpoints) = {len(edges_in_range)}")

uf = UnionFind(in_range_ids)
for a, b, _w in edges_in_range:
    uf.union(a, b)

components = defaultdict(list)
for nid in in_range_ids:
    components[uf.find(nid)].append(nid)
component_sizes = sorted((len(v) for v in components.values()), reverse=True)
log(f"connected components (sizes, largest first) = {component_sizes}")

largest_root = max(components, key=lambda k: len(components[k]))
final_node_ids = set(components[largest_root])
final_edges = [
    (a, b, w) for (a, b, w) in edges_in_range if a in final_node_ids and b in final_node_ids
]
log(f"final graph: nodes = {len(final_node_ids)}, edges = {len(final_edges)}")

# reproject nodes to local metric coordinates
nodes_gdf = nodes_gdf.set_index("node_id")
nodes_proj = nodes_gdf.to_crs(PROJ_CRS)

# Three.js mapping: projected X -> three.js x, projected Y (north) -> three.js -z,
# ordinal*FLOOR_HEIGHT_M -> three.js y (height). See README / plan decision 8.
node_local = {}
for nid in final_node_ids:
    px, py = nodes_proj.loc[nid].geometry.x, nodes_proj.loc[nid].geometry.y
    ordinal = float(nodes_gdf.loc[nid, "ordinal"])
    lx = px - ref_x
    ly = py - ref_y
    node_local[nid] = {
        "id": nid,
        "x": lx,
        "y": ordinal * FLOOR_HEIGHT_M,
        "z": -ly,
        "floorOrdinal": ordinal,
    }

graph_nodes = list(node_local.values())
graph_edges = [{"from": a, "to": b, "weight": w} for (a, b, w) in final_edges]

# index of final nodes by floor ordinal, for nearest-node POI snapping
nodes_by_ordinal = defaultdict(list)
for nid in final_node_ids:
    ordinal = float(nodes_gdf.loc[nid, "ordinal"])
    px, py = nodes_proj.loc[nid].geometry.x, nodes_proj.loc[nid].geometry.y
    nodes_by_ordinal[ordinal].append((nid, px, py))

# ---------------------------------------------------------------------------
# 3. Space polygons -> floors.geojson (within 450m, projected/local coords)
# ---------------------------------------------------------------------------
floor_features = []
space_kept = 0
space_total = 0
space_ordinal_missing = 0

for space_path in find_space_shapefiles():
    dir_path, prefix = prefix_for(space_path)
    space_gdf = gpd.read_file(space_path, encoding="utf-8")
    space_total += len(space_gdf)
    if space_gdf.empty:
        continue
    space_proj = space_gdf.to_crs(PROJ_CRS)
    ordinal_map = load_floor_ordinal_map(dir_path, prefix)

    for idx in range(len(space_proj)):
        geom = space_proj.geometry.iloc[idx]
        rep = geom.centroid
        dist = math.hypot(rep.x - ref_x, rep.y - ref_y)
        if dist > RADIUS_M:
            continue

        row = space_gdf.iloc[idx]
        ordinal = ordinal_map.get(row["floor_id"])
        if ordinal is None:
            space_ordinal_missing += 1
            continue
        ordinal = float(ordinal)

        # translate to local origin, keep as flat (x, y) meters; the web app
        # applies the same x/-z/height transform as graph nodes when extruding.
        translated = translate_geom(geom, -ref_x, -ref_y)

        floor_features.append(
            {
                "type": "Feature",
                "properties": {
                    "floorOrdinal": ordinal,
                    "toll": row.get("toll"),
                    "source": row.get("source"),
                },
                "geometry": geom_to_geojson(translated),
            }
        )
        space_kept += 1

log(f"space features total = {space_total}, kept (within {RADIUS_M:.0f}m) = {space_kept}, "
    f"missing floor ordinal = {space_ordinal_missing}")

floors_geojson = {"type": "FeatureCollection", "features": floor_features}

# ---------------------------------------------------------------------------
# 4. POI naming: Opening (gates) + Facility(category==F108, exits)
# ---------------------------------------------------------------------------
def find_named_shapefiles(suffix):
    pattern = os.path.join(EXTRACTED_ROOT, "**", f"*_{suffix}.shp")
    paths = glob.glob(pattern, recursive=True)
    return [p for p in paths if os.path.normpath(NW_DIR) not in os.path.normpath(p)]


# 建物/路線フォルダのファイル名prefix(末尾のフロア部分を除いたもの)から、
# UIに表示する路線名・建物名へのマッピング。「東改札」等の改札名は路線ごとに重複するため、
# 出発地/目的地選択時に区別できるよう付加情報として使う。
LINE_LABELS = {
    "ChiyodaOtemati": "東京メトロ千代田線",
    "MaruOtemati": "東京メトロ丸ノ内線",
    "MitaOtemati": "都営三田線",
    "Hanzo": "東京メトロ半蔵門線",
    "Tozai": "東京メトロ東西線",
    "MaruTokyo": "東京メトロ丸ノ内線(東京駅)",
    "ChiyodaHibiya": "東京メトロ千代田線(日比谷駅)",
    "ChiyodaNiju": "東京メトロ千代田線(二重橋前駅)",
    "GinzaGinza": "東京メトロ銀座線(銀座駅)",
    "HibiyaGinza": "東京メトロ日比谷線(銀座駅)",
    "HibiyaHibiya": "東京メトロ日比谷線(日比谷駅)",
    "HibiyaHigagin": "都営地下鉄(東銀座駅付近)",
    "MaruGinza": "東京メトロ丸ノ内線(銀座駅)",
    "MitaHibiya": "都営三田線(日比谷駅)",
    "Yurakucho": "東京メトロ有楽町線",
    "YurakuTika": "有楽町地下街",
    "JRTokyoSta": "JR東京駅",
    "MARUBIRU": "丸ビル",
    "SHINMARUBIRU": "新丸の内ビル",
    "TOKIA": "TOKIA",
    "BRICK": "丸の内ブリックスクエア",
    "EIRAKU": "イーヨ",
    "MITSUUFJ": "三菱UFJ信託銀行本店ビル",
    "OAZO": "丸の内オアゾ",
    "MITSUBISHISHOJI": "三菱商事ビル",
    "KITTE": "KITTE",
    "KOUTUU": "東京交通会館",
    "ITOCIA": "有楽町イトシア",
    "MARION": "有楽町マリオン",
    "OOTEMORI": "オーテモリ",
    "FORUM": "東京国際フォーラム",
    "TEKKOU": "鉄鋼ビルディング",
}


def line_label_for(prefix):
    """'ChiyodaOtemati_B1' -> 'ChiyodaOtemati' -> '東京メトロ千代田線'(未知ならキーそのもの)。"""
    key = prefix.rsplit("_", 1)[0]
    return LINE_LABELS.get(key, key)


poi_candidates = []  # (name, ordinal, px, py, prefix, source_desc)
for suffix in ("Opening", "Facility"):
    for shp_path in find_named_shapefiles(suffix):
        dir_path = os.path.dirname(shp_path)
        base = os.path.basename(shp_path)
        prefix = base[: -len(f"_{suffix}.shp")]
        gdf = gpd.read_file(shp_path, encoding="utf-8")
        if gdf.empty:
            continue
        if suffix == "Facility":
            gdf = gdf[gdf["category"] == "F108"]
            if gdf.empty:
                continue
        ordinal_map = load_floor_ordinal_map(dir_path, prefix)
        proj = gdf.to_crs(PROJ_CRS)
        for idx in range(len(gdf)):
            row = gdf.iloc[idx]
            name = row.get("name")
            if not name:
                continue
            geom_proj = proj.geometry.iloc[idx]
            rep = geom_proj.centroid
            dist_ref = math.hypot(rep.x - ref_x, rep.y - ref_y)
            if dist_ref > RADIUS_M:
                continue
            ordinal = ordinal_map.get(row["floor_id"])
            if ordinal is None:
                continue
            ordinal = float(ordinal)
            poi_candidates.append(
                {
                    "name": name,
                    "ordinal": ordinal,
                    "x": rep.x,
                    "y": rep.y,
                    "prefix": prefix,
                    "source": f"{prefix}_{suffix}#{idx}",
                }
            )

log(f"poi candidate features (Opening + Facility F108, within range, named) = {len(poi_candidates)}")

# for each candidate, find nearest same-floor node; keep best (min distance) per node
best_for_node = {}  # node_id -> (dist, name, source)
failed_pois = []  # candidates with no node within POI_SNAP_M

for cand in poi_candidates:
    same_floor_nodes = nodes_by_ordinal.get(cand["ordinal"], [])
    best_nid, best_dist = None, None
    for nid, px, py in same_floor_nodes:
        d = math.hypot(px - cand["x"], py - cand["y"])
        if best_dist is None or d < best_dist:
            best_dist, best_nid = d, nid
    if best_nid is None or best_dist > POI_SNAP_M:
        failed_pois.append(
            {
                "name": cand["name"],
                "ordinal": cand["ordinal"],
                "source": cand["source"],
                "nearest_dist_m": None if best_dist is None else round(best_dist, 1),
            }
        )
        continue
    prev = best_for_node.get(best_nid)
    if prev is None or best_dist < prev[0]:
        best_for_node[best_nid] = (best_dist, cand["name"], cand["prefix"])

pois = []
for nid, (dist, name, prefix) in best_for_node.items():
    n = node_local[nid]
    pois.append(
        {
            "id": nid,
            "nodeId": nid,
            "name": name,
            "group": line_label_for(prefix),
            "floorOrdinal": n["floorOrdinal"],
            "x": n["x"],
            "y": n["y"],
            "z": n["z"],
        }
    )

log(f"selectable (named) nodes = {len(pois)}")
log(f"POIs that failed to snap within {POI_SNAP_M:.0f}m = {len(failed_pois)}")
for f in failed_pois:
    log(f"  FAILED: name={f['name']!r} ordinal={f['ordinal']} source={f['source']} "
        f"nearest_dist_m={f['nearest_dist_m']}")

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------
os.makedirs(OUT_DIR, exist_ok=True)

# NaN/Infinityは標準JSONで表現できず、書き出すとブラウザ側のJSON.parse/Viteの
# JSONインポートが壊れるため、書き出し直前にnullへ置き換えて検出する。
nan_stats = {"count": 0}
floors_geojson = sanitize_nan(floors_geojson, nan_stats)
graph_payload = sanitize_nan({"nodes": graph_nodes, "edges": graph_edges}, nan_stats)
pois = sanitize_nan(pois, nan_stats)
if nan_stats["count"] > 0:
    msg = (
        f"WARNING: {nan_stats['count']} NaN/Infinity value(s) found in source data; "
        "replaced with null before writing JSON."
    )
    log(msg)
    print(msg)

with open(os.path.join(OUT_DIR, "floors.geojson"), "w", encoding="utf-8") as f:
    json.dump(floors_geojson, f, ensure_ascii=False, allow_nan=False)

with open(os.path.join(OUT_DIR, "graph.json"), "w", encoding="utf-8") as f:
    json.dump(graph_payload, f, ensure_ascii=False, allow_nan=False)

with open(os.path.join(OUT_DIR, "pois.json"), "w", encoding="utf-8") as f:
    json.dump(pois, f, ensure_ascii=False, allow_nan=False)

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines) + "\n")

print("build_geojson.py done. See scripts/build_report.txt for the summary.")
