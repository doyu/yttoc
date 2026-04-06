# yttoc：段階的実装計画

## 設計哲学

**「動くものを今日作り、毎週少しずつ賢くする」**

各フェーズは前のフェーズの出力をそのまま入力として使える。
途中で止めても、そのフェーズ単体で十分に価値がある。

---

## Phase 0：手動ベースライン（Day 1 — 道具はClaude.aiだけ）

### やること
Claude.aiにXscriptを貼って、1プロンプトでToCを生成する。
これが「品質のベースライン」になる。今後のすべての改善はこれとの比較で評価する。

### プロンプト（そのまま使える）

```
あなたはYouTube動画の構造化エディターです。

以下はYouTube動画のXscriptです。
動画情報：
- タイトル: {title}
- チャンネル: {channel}
- URL: {url}

## タスク
1. Xscriptを読み、話題の転換点を特定してください
2. 各セクションについて以下を出力してください：
   - タイムスタンプ（MM:SS）
   - セクションタイトル（日本語・簡潔に）
   - 1-2文の要約
   - 登場した重要キーワード（人名、技術用語、固有名詞）

## 出力フォーマット（Markdown）
### Table of Contents
- MM:SS - セクションタイトル
  - MM:SS - サブセクション（あれば）

### セクション詳細
#### MM:SS - セクションタイトル
**要約:** ...
**キーワード:** ...
**Evidence:** "原文の該当箇所の引用（英語のまま）" [MM:SS]

## 制約
- セクション数は7〜15が目安
- 要約は必ず日本語
- Evidenceは原文のまま（翻訳しない）
- タイムスタンプはXscriptの実際の時間に忠実に
```

### 得られるもの
- ToC + セクション要約 + キーワード + Evidence付き
- **これ自体がすでに十分使える**。2時間動画でも10分で「検索可能な地図」が手に入る

### 限界（＝次のフェーズで解決すること）
- 長尺動画（90分超）でコンテキストウィンドウに収まらない
- LLMが中盤のセクションを雑に扱う傾向
- 毎回手動コピペが面倒

---

## Phase 1：Xscriptパース＆チャンク分割

### 動機
Phase 0の最大の問題「長尺動画が入らない」「中盤が雑になる」を解決する。

### nbdev開発手順

1. `nbs/01_xscript.ipynb` で探索
   - YouTube xscript の実フォーマットを観察（手動コピペ、yt-dlp SRT等）
   - パース処理のプロトタイプ
2. 動作確認後、`#| export` でモジュール化 → `yttoc/xscript.py`

### 対象機能
- `parse_xscript`: タイムスタンプ付きテキストをパース
- `chunk_by_time`: 時間ベースでチャンク分割（オーバーラップ付き）
- `format_chunk`: LLMに渡すフォーマットで文字列化

### Phase 1のワークフロー
```bash
# 1. Xscriptをテキストファイルに保存
# 2. yttocでチャンク分割
python -m yttoc.xscript input.txt ./chunks/

# 3. 各チャンクをClaude.aiに手動で貼ってPhase 0のプロンプトで要約
# 4. 全チャンクの要約を集めて、ToC統合プロンプトを実行
```

### ToC統合プロンプト（チャンク要約を集めた後に使う）

```
以下は動画の各チャンク（2分単位）の要約です。

## タスク
1. 隣接するチャンクで同じ話題が続いている場合は統合してください
2. 話題の転換点を特定し、階層的なTable of Contentsを作成してください
3. 各セクションのキーワードを統合してください

## 出力フォーマット
### Table of Contents
- MM:SS - メインセクション
  - MM:SS - サブセクション

### Entities（動画全体の登場キーワード）
#タグ1, #タグ2, ...

### セクション詳細
（各セクションの統合要約 + Evidence）
```

### Phase 0との差分
- 長尺動画に対応できる
- 中盤の情報落ちが大幅に減る（各チャンクを均等に処理するため）
- まだ手動コピペは残るが、品質は段違い

---

## Phase 2：API自動化

### 動機
Phase 1の手動コピペを自動化する。ここからが「プログラム」になる。

### nbdev開発手順

1. `nbs/02_summarize.ipynb` で探索
   - Anthropic API でチャンク要約のプロトタイプ
   - Haiku/Sonnet の使い分け検証
2. 動作確認後、`#| export` でモジュール化 → `yttoc/summarize.py`

### 対象機能
- `summarize_chunk`: 1チャンクをAPI経由で要約（Haiku）
- `merge_summaries`: チャンク要約を統合してToC生成（Sonnet）
- 並行処理（asyncio + semaphore）

### 2層アーキテクチャ
- **Layer A** (Haiku): 各チャンクの個別要約（大量・並行処理）
- **Layer B** (Sonnet): チャンク要約の統合・構造化（1回）

### Phase 1との差分
- 手動コピペが完全不要
- Haiku/Sonnetの使い分けでコスト最適化
- 中間結果（summaries.json）が残るのでデバッグ・再実行が容易
- 並行処理で2時間動画でも1-2分で完了

---

## Phase 3：品質強化

### 3a. トピック境界検知の改善
- `nbs/03_drift.ipynb` で探索 → `yttoc/drift.py`
- 隣接チャンク間のトピックドリフトスコア（0-10）を算出
- Haikuで十分な軽量タスク

### 3b. 出力フォーマッタ
- `nbs/04_formatter.ipynb` で探索 → `yttoc/formatter.py`
- Obsidian互換Markdown出力（frontmatter + timestamp links）

### 3c. Xscript自動取得（オプション）
- yt-dlp連携で YouTube URL → xscript を自動化

### Phase 2との差分
- トピック境界の精度が上がる（ドリフトスコア）
- Obsidianに直接投入できるフォーマット
- YouTube URLだけで全自動化（yt-dlp連携）

---

## Phase 4：RAGエンジン化（必要になったら）

Phase 3までで「動画を構造化メモにする」目的は十分達成できる。
Phase 4に進むのは以下の条件を満たした時：

- 処理した動画が50本を超えた
- 「あの動画で誰かがXXについて言ってたけど、どれだっけ？」が頻発する
- 動画横断で知識を検索したい

### 構成要素
1. **ベクトルDB**：Chroma or Qdrant（ローカル）に要約 + 原文チャンクを格納
2. **Parent-Child Retrieval**：要約で検索 → 原文チャンクで回答生成
3. **QA Interface**：CLIまたはStreamlitで質問応答

---

## nbdev モジュール対応表

| Notebook | Module | Phase | パイプライン |
|----------|--------|-------|------------|
| `nbs/00_core.ipynb` | `yttoc/core.py` | — | 共通ユーティリティ |
| `nbs/01_fetch.ipynb` | `yttoc/fetch.py` | 3c→先行 | YouTube取得 |
| `nbs/02_xscript.ipynb` | `yttoc/xscript.py` | 1 | SRTパース＆チャンク分割 |
| `nbs/03_summarize.ipynb` | `yttoc/summarize.py` | 2 | LLM要約（Haiku+Sonnet） |
| `nbs/04_drift.ipynb` | `yttoc/drift.py` | 3a | トピック境界検知 |
| `nbs/05_formatter.ipynb` | `yttoc/formatter.py` | 3b | Obsidian Markdown出力 |

---

## コスト見積もり（Phase 2基準）

| 動画長 | チャンク数 | Layer A (Haiku) | Layer B (Sonnet) | 合計目安 |
|--------|-----------|-----------------|------------------|---------|
| 30分   | ~15       | ~$0.01          | ~$0.02           | ~$0.03  |
| 1時間  | ~30       | ~$0.02          | ~$0.03           | ~$0.05  |
| 2時間  | ~60       | ~$0.04          | ~$0.05           | ~$0.09  |

---

## 今日やること

1. **Phase 0を1本の動画で試す**（15分で完了）
2. 出力を眺めて「ここがもっと良くなればいいな」をメモする
3. そのメモがPhase 1以降の優先順位を決める

最も重要なのは**Phase 0で「良いToCとは何か」の感覚を掴むこと**。
ツールを作る前に、自分の目で品質基準を確立する。
