# yttoc：段階的実装計画

## 設計哲学

**「動くものを今日作り、毎週少しずつ賢くする」**

各フェーズは前のフェーズの出力をそのまま入力として使える。
途中で止めても、そのフェーズ単体で十分に価値がある。

---

## Phase 0：手動ベースライン（Day 1）

### やること
ダウンロード済み transcript をそのまま Claude.ai に渡し、1回で英語の ToC と summary を作る。
これを品質ベースラインにし、以後の自動化はこの出力と比較して評価する。

### プロンプト（そのまま使える）

```text
You are a structural editor for YouTube video transcripts.

Video info:
- Title: {title}
- Channel: {channel}
- URL: {url}

Task
1. Read the transcript and identify topic transitions.
2. For each section, output:
   - timestamp (MM:SS)
   - concise English section title
   - 1-2 sentence English summary
   - important keywords (people, technical terms, proper nouns)

Output format (Markdown)
### Table of Contents
- MM:SS - Section title

### Section Details
#### MM:SS - Section title
**Summary:** ...
**Keywords:** ...
**Evidence:** "quoted transcript text" [MM:SS]

Constraints
- Aim for 7-15 sections
- Write titles and summaries in English
- Keep Evidence in original wording
- Be faithful to transcript timestamps
```

### 得られるもの
- ToC + section summaries + keywords + evidence
- これ自体が品質ベースラインになる

### 限界（＝次のフェーズで解決すること）
- 毎回手動コピペが必要
- 実行ごとに section 番号や境界が揺れる
- 構造データや summary をローカルに再利用できない

---

## Phase 1：Transcriptパース＆正規化

### 動機
ToC 生成や summary 生成の前に、`captions.*.srt` を安定した内部表現に変換できるようにする。
notebook / module 名は `xscript` のまま維持するが、役割は transcript のパースと正規化である。

### nbdev開発手順

1. `nbs/02_xscript.ipynb` で `captions.*.srt` を観察
2. SRT を `start`, `end`, `text` の正規化された配列に変換する
3. 必要な range extraction helper を追加する
4. 動作確認後、`#| export` でモジュール化 → `yttoc/xscript.py`

### 対象機能
- `parse_xscript`: `captions.*.srt` を正規化された transcript segment 列に変換
- range extraction helper: `start/end` で transcript を切り出す

### 初期版の前提
- 入力は `captions.*.srt`（`ja` or `en`）のみ
- 正規化結果はファイルに保存しない
- 毎回 `captions.*.srt` から on-demand でパースする
- `chunk_by_time` は入れない。必要になった時の最適化として後ろに回す

### この段階で使えるCLI
- `yttoc-fetch <url>`
- `yttoc-list`
- `yttoc-raw <video_id>`

### ワークフロー
```bash
vid=$(yttoc-fetch https://youtube.com/watch?v=xxx)
yttoc-raw "$vid"
```

### Phase 0との差分
- transcript をローカルキャッシュから再利用できる
- `video_id` ベースで対象動画を明示できる
- 後続の ToC / summary が同じ transcript 正規化処理を共有できる

---

## Phase 2a：ToC generation

### 動機
`toc`, section 指定の `raw`, `sum` が共有する構造データを先に確定させる。
`toc.json` は表示用ではなく、section 境界の権威データとして扱う。

### nbdev開発手順

1. `nbs/03_toc.ipynb` で全文 transcript から ToC を作るプロトタイプを試す
2. LLM には strict structured output を要求し、`title`, `start` の section list を返させる
3. アプリ側で `path` と `end` を補完し、整合性を検証する
4. 動作確認後、`#| export` でモジュール化 → `yttoc/toc.py`

### 対象機能
- 全文 transcript から ToC を生成
- LLM 出力の section list を検証し、`path` と `end` を補完
- `toc.json` を書き出す

### `toc.json` の最小形
```json
{
  "sections": [
    {"path": "1", "title": "Introduction", "start": 0, "end": 750},
    {"path": "2", "title": "Setting up the server", "start": 750, "end": 2700}
  ]
}
```

### 構造上の制約
- section は 1 段構造のみ
- sections は動画全体を連続的に覆う
- `path` はアプリ側で採番する
- `end` は sibling の `start` と動画 duration から補完する

### 正規化と失敗条件
- 最小限の normalize だけ行う
  - `start` 昇順に並べる
  - 重複 `start` を落とす
  - 最初の section `start` が 0 でなければ 0 に補正する
- section coverage が壊れていたら失敗する
- 推測による大幅修復はしない

### この段階で使えるCLI
- `yttoc-toc <video_id>`
- `yttoc-raw <video_id> <section>`

### Phase 1との差分
- section 番号と時間範囲が `toc.json` で固定される
- `raw <video_id> <section>` が安定して使える
- `sum` が参照する構造データが明確になる

---

## Phase 2b：Summaries

### 動機
構造が固定された後に、section 単位と動画全体の summary を安定して再利用できるようにする。

### nbdev開発手順

1. `nbs/04_summarize.ipynb` で `toc.json` を前提に section summary を作るプロトタイプを試す
2. 全 section の英語 summary を一括生成する
3. section summary 群を統合して `full` summary を作る
4. 動作確認後、`#| export` でモジュール化 → `yttoc/summarize.py`

### 対象機能
- 全 section の英語 summary を一括生成
- section summary 群から動画全体の `full` summary を生成
- `summaries.json` を書き出す

### `summaries.json` の最小形
```json
{
  "full": {
    "summary": "...",
    "keywords": ["..."],
    "evidence": {"text": "...", "at": 2712}
  },
  "sections": {
    "3": {
      "summary": "...",
      "keywords": ["..."],
      "evidence": {"text": "...", "at": 2712}
    }
  }
}
```

### 初期版の前提
- summary は英語のみ
- `sum <video_id>` の初回は全 section summary + `full` をまとめて生成する
- `sum <video_id> <section>` でも初回は同じく全 section を生成し、その後に指定 section を表示する
- `toc.json` が無ければ `sum` の内部で先に生成する

### この段階で使えるCLI
- `yttoc-sum <video_id>`
- `yttoc-sum <video_id> <section>`

### Phase 2aとの差分
- section ごとの summary が安定して再利用できる
- `full` summary を section summary 群の統合として保持できる
- `summaries.json` が `toc.json` に従属する形でキャッシュされる
- 1 段 section のみなので、親子の二重要約を避けられる

---

## Phase 3：将来の拡張候補

### 3a. Transcript自動取得 → 実装済み・前提機能化
- `nbs/01_fetch.ipynb` → `yttoc/fetch.py`
- もともとは後半の optional automation として構想した
- ただし実装を進める中で、日常 CLI の入口機能として先行実装した
- 現在は `yttoc-fetch <url>` と `yttoc-list` を支える前提機能として扱う

### 3b. 必要になったら追加するもの
- ToC 境界精度が不足したら、drift のような補助ロジックを追加する
- CLI 標準出力以外の Markdown / Obsidian 向け整形が必要になったら formatter を追加する
- どちらも初期版では notebook を作らない

### Phase 2との差分
- transcript 取得は後半機能ではなく、全フェーズの入口として機能する
- drift / formatter は初期スコープから外し、必要時にだけ導入する

---

## Phase 4：RAGエンジン化（必要になったら）

Phase 2までで「動画を構造化メモにする」目的は十分達成できる。
Phase 4に進むのは以下の条件を満たした時：

- 処理した動画が50本を超えた
- 「あの動画で誰かがXXについて言ってたけど、どれだっけ？」が頻発する
- 動画横断で知識を検索したい

### 構成要素
1. ベクトル DB に summary + transcript range を格納する
2. summary で検索し、対応する原文範囲で回答を組み立てる
3. CLI または Web UI で質問応答する

---

## CLI設計（target UI）

**方針：** nbdev デファクトに従い、`@call_parse` で関数単位の個別コマンド。`pyproject.toml` の `[project.scripts]` で登録。現在動画の暗黙 state は持たず、毎回 `video_id` を明示する。

### コマンド

```bash
yttoc-fetch <url>
yttoc-list
yttoc-toc <video_id>
yttoc-sum <video_id> [section]
yttoc-raw <video_id> [section]
```

`section` は `3` 形式。`video_id` は完全一致のみ受け付ける。

### daily flow

```bash
vid=$(yttoc-fetch https://youtube.com/watch?v=xxx)
yttoc-toc "$vid"
yttoc-sum "$vid"
yttoc-raw "$vid"
```

補助フロー：

```bash
yttoc-list
yttoc-sum "$vid" 3
yttoc-raw "$vid" 3
```

### フェーズごとの利用可能コマンド

- fetch 先行実装段階
  - `yttoc-fetch <url>`
  - `yttoc-list`
- Phase 1 完了後
  - `yttoc-raw <video_id>`
- Phase 2a 完了後
  - `yttoc-toc <video_id>`
  - `yttoc-raw <video_id> <section>`
- Phase 2b 完了後
  - `yttoc-sum <video_id>`
  - `yttoc-sum <video_id> <section>`

### キャッシュレイアウト

```text
~/.cache/yttoc/<video_id>/
  meta.json
  captions.ja.srt   # if Japanese captions exist
  captions.en.srt   # otherwise fall back to English
  toc.json
  summaries.json
```

- 字幕ファイルは `captions.{lang}.srt` 形式。`ja` 優先、無ければ `en` にフォールバック
- `transcript.json` は作らない
- transcript の正規化は毎回 `captions.*.srt` から行う
- `toc.json` は構造の権威データ
- `summaries.json` は `toc.json` に従属する派生キャッシュ
- キャッシュ済み動画は再 fetch しない。字幕言語を変えたい場合は `--refresh` で再取得する（将来実装）

### `meta.json` に入れるもの

- `id`
- `title`
- `channel`
- `duration`
- `upload_date`
- `webpage_url`
- `description` — 動画説明文。手動 ToC やゲスト情報を含むことが多く、ToC/summary 生成時の背景情報として使う
- `captions` — 取得済み字幕の言語と種別の dict（例: `{"ja": "manual"}`）。旧形式の `caption_type` は `yttoc_list` で後方互換処理あり
- `last_used_at`

### 各コマンドの挙動

- `fetch`
  - 単一動画 URL のみ対応
  - 字幕選択: `ja` manual → `ja` auto → `en` manual → `en` auto の優先順で最初に見つかった言語を取得
  - 成功時は `video_id` だけを stdout に 1 行で出す
  - 進捗や cache hit などの人間向けメッセージは stderr に出す
  - 既にキャッシュ済み（`captions.*.srt` が存在）なら再取得しない
  - 成功時に `last_used_at` を更新する
- `list`
  - `meta.json` と `captions.*.srt` が揃っている動画だけを表示する
  - 取得済み言語を `[ja]` / `[en]` のように表示する
  - `last_used_at` 降順に並べる
- `raw`
  - `raw <video_id>` は全文 transcript を表示する
  - `raw <video_id> <section>` は `toc.json` 必須。無ければ失敗する
  - 成功時に `last_used_at` を更新する
- `toc`
  - 初回は全文 transcript から `toc.json` を lazy 生成する
  - 成功時に `last_used_at` を更新する
- `sum`
  - `toc.json` が無ければ内部で先に生成する
  - 初回は全 section summary + `full` をまとめて生成する
  - 成功時に `last_used_at` を更新する

### refresh の扱い

- `yttoc-toc <video_id> --refresh`
  - 新しい `toc.json` を生成して validate する
  - 成功したら atomic に置き換える
  - その後で `summaries.json` を削除する
- `yttoc-sum <video_id> --refresh`
  - 新しい `summaries.json` を生成して validate する
  - 成功したら atomic に置き換える
- `yttoc-fetch <url> --refresh`
  - 初期版では入れない

### 出力フォーマット

**`fetch`**
```text
abc123xyz89
```

**`list`**
```text
VIDEO_ID      LAST_USED           DUR      TITLE
abc123xyz89   2026-04-06 14:22    2:16:32  Sysadmin, devops, and web scraping - Solveit lesson 6
```

**共通ヘッダー（`toc` / `sum` / `raw`）**
```text
# {title}
Channel: {channel} | Duration: {duration} | {upload_date}
```

**`toc`**
```text
1. Introduction 00:00-12:30 (12m30s) https://youtube.com/watch?v=xxx&t=0
2. Setting up the server 12:30-45:00 (32m30s) https://youtube.com/watch?v=xxx&t=750
```

**`sum`**
```text
## 3. Web scraping (45:00)
This section introduces web scraping using Python...
**Keywords:** BeautifulSoup, requests, CSS selectors
**Evidence:** "so the first thing we need to do is..." [45:12]
```

**`raw`**
```text
## 3. Web scraping (45:00 - 1:12:30)
[45:00] so the first thing we need to do is install...
[45:12] beautifulsoup4 requests and then we can...
```

### 設計判断

- `set` / `use` / 現在動画の永続 state は持たない
- 短縮は shell 側で吸収する。CLI 自体は明示的に保つ
- `video_id` は exact match のみ
- `toc.json` が section 境界の権威データ
- `summaries.json` は `toc.json` 依存の派生キャッシュ
- 字幕取得は `ja` 優先 → `en` フォールバック。ToC / summary の出力言語は英語
- キャッシュ済み動画の字幕言語変更は `--refresh` で対応（将来実装）
- chunking は deferred optimization とし、必要になるまで入れない

---

## nbdev モジュール対応表

| Notebook | Module | Phase | パイプライン |
|----------|--------|-------|------------|
| `nbs/00_core.ipynb` | `yttoc/core.py` | — | 共通ユーティリティ |
| `nbs/01_fetch.ipynb` | `yttoc/fetch.py` | 3c→先行 | Transcript取得 |
| `nbs/02_xscript.ipynb` | `yttoc/xscript.py` | 1 | Transcriptパース＆正規化 |
| `nbs/03_toc.ipynb` | `yttoc/toc.py` | 2a | ToC generation |
| `nbs/04_summarize.ipynb` | `yttoc/summarize.py` | 2b | Section/full summaries |

---

## コスト見積もり

初期版は transcript 全文ベースの ToC / summary を優先し、provider・prompt・refresh 戦略の詳細は後で固める。
そのため、現時点では数値コスト見積もりを固定しない。
長尺動画やコスト最適化が問題になった時点で、chunking や軽量モデル分割を導入する。

---

## 今日やること

1. `fetch` / `list` / `raw` を土台にした daily CLI を固める
2. `xscript` モジュールで transcript パース＆正規化を実装する
3. `toc.json` を生成する最小構造パイプラインを作る

最初に作るべきなのは「毎日触れる最小の道具」。
chunking や多言語化は、実際に必要になった時だけ追加する。
