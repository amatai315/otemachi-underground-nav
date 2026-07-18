# 大手町地下移動ナビ (PoC)

東京都ハッカソン向けプロトタイプ。大手町駅周辺の地下コンコースを実データから起こした簡易3D空間で表示し、
出発地(改札)・目的地(改札/出口)を選ぶと、実際の歩行者ネットワークデータ上でダイクストラ法により
最短経路を計算し、3D空間上にハイライト表示します。スマートフォン縦画面での利用を前提としています。

## 構成

- `scripts/build_geojson.py` — 元データ(Shapefile)を読み込み、`web/src/data/` 用の
  GeoJSON/JSONへ変換するローカル専用パイプライン(Viteビルドには含まれません。手動実行が必要)。
- `web/` — Vite + Vanilla JS + Three.js のフロントエンドアプリ本体。

## データソース・クレジット

- **東京駅周辺屋内地図オープンデータ(令和2年度更新版)**
  - 提供: 国土交通省「高精度測位社会プロジェクト」
  - 公開: G空間情報センター (https://www.geospatial.jp/ckan/dataset/mlit-indoor-tokyo-r2)
  - 形式: Shapefile(通路・部屋ポリゴン、歩行者ネットワーク、改札・出口等のPOI属性を含む)
- 本リポジトリには元データそのもの(`raw-data/`)は含まれていません(ライセンス上の再配布可否が
  明確でないため `.gitignore` で除外)。`web/src/data/` に含まれる変換済みJSON/GeoJSONは、
  `scripts/build_geojson.py` によって上記データから加工・抽出した成果物です。
  データを再取得して自分でパイプラインを再実行する場合は、G空間情報センターでのユーザー登録
  (無償)の上で元データをダウンロードし、`raw-data/extracted/` 以下に展開してください。

## データパイプラインの再実行(必要な場合のみ)

`web/src/data/floors.geojson` / `graph.json` / `pois.json` は生成済みでリポジトリに含まれているため、
通常はこの手順は不要です。元データを更新した場合のみ実行してください。

```bash
pip install geopandas fiona pyproj shapely
PYTHONIOENCODING=utf-8 python scripts/build_geojson.py
```

実行後、`scripts/build_report.txt` にノード数・エッジ数・連結成分サイズ・POIスナップの
成否サマリーが出力されます。

## ローカルでの動かし方

```bash
cd web
npm install
npm run dev
```

表示された `http://localhost:5173/` 等のURLをブラウザで開いてください。スマホでの見た目を
確認する場合は、ブラウザのDevTools(スマホ縦画面のデバイスエミュレーション、375〜430px幅程度)
を使うか、同一ネットワーク内のスマホから `npm run dev -- --host` で立てたアドレスにアクセス
してください。

## ビルド

```bash
cd web
npm run build
```

`web/dist/` に静的ファイル一式が出力されます。`vite.config.js` で `base: './'`(相対パス)を
設定しているため、どのサブパスに配置してもそのまま動作します。`npm run preview` でビルド結果を
ローカル確認できます。

## GitHub Pagesへのデプロイ

このリポジトリは https://github.com/amatai315/otemachi-underground-nav にあり、
GitHub Pagesで公開済みです。

- 公開URL: https://amatai315.github.io/otemachi-underground-nav/
- Pages設定: Source = `gh-pages` ブランチ / `/(root)`(`gh-pages` npmパッケージが
  ブランチを作成した際にGitHub側で自動的に有効化されました)

### 再デプロイ手順(コードを更新した場合)

`web/` に `gh-pages` パッケージを導入済みです。ビルドして `gh-pages` ブランチへ
pushするだけで再公開されます。

```bash
cd web
npm run deploy
```

内部的には `vite build && gh-pages -d dist` を実行し、`web/dist` の内容を
`gh-pages` ブランチへコミット・pushします(mainブランチには影響しません)。
数十秒〜1分程度でPages側のビルドが反映されます。

`base: './'` により相対パスでビルドされているため、リポジトリ名やGitHubアカウント名が
変わらない限り `vite.config.js` の変更は不要です。

### 別アカウント/別リポジトリで新規にセットアップする場合

1. GitHub上で新規リポジトリを作成し、ローカルのプロジェクトルートをそのリモートにpushする。
2. `cd web && npm install -D gh-pages`(このリポジトリでは導入済み)。
3. `npm run deploy` を実行する。
4. 初回は数分待ってから、GitHubリポジトリの Settings → Pages で Source が
   `gh-pages` ブランチになっていることを確認する(通常は自動で設定される)。

## 既知の簡略化事項

- **フロア高さは近似値**です。元データに標高・階高情報が無い(2.5Dデータ)ため、
  `y = ordinal * 4.0`(メートル)という単純な換算で各階を積み上げています。実際の
  スラブ高さは建物ごとに異なるため、フロア間の見た目上の重なりは正確ではありません。
- **POIの位置合わせ(スナップ)には25mの許容誤差**があります。改札・出口(POI)の座標を、
  同じ階の最寄りの歩行者ネットワークノードに紐づけていますが、25m以内に該当ノードが
  見つからなかったPOIはリストから除外されます(`scripts/build_report.txt` で一覧を確認可能)。
- **`toll`(有料/無料)以外の分類コードの意味は不明**です。元データセットに凡例(コード表)が
  同梱されていないため、通路ポリゴンの色分けは `toll` フィールド(改札内寄り/公共通路)の
  区別にとどめており、部屋種別ごとの詳細な描き分けは行っていません。
- 実測位(GPS/PDR)、PC/タブレット向けレイアウト、バリアフリー経路の重み付け、
  サーバーサイド処理は本PoCのスコープ外です。
