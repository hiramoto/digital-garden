# Vault → notes.kazaimu.com 同期手順

Googleドライブ上のObsidian Vault（`マイドライブ/.../obsidian`）から、フロントマターに
`publish: true` があるノートだけを `content/` にコピーし、main に push する。
Cloudflare Pages が push を検知してビルド・公開する。

この手順は定期タスク（クラウド）から Claude が実行する前提で書いている。

## 仕組み

- Drive にはコネクタ（`search_files` / `get_file_metadata` / `download_file_content`）でしか
  届かないので、`scripts/garden_sync.py` はツールの結果をセッションの記録
  （`~/.claude/projects/**/*.jsonl` と `tool-results/*.txt`）から読み、base64 をそのまま
  デコードして書き出す。**ノート本文をモデルが書き写すことは一切しない。**
- 書き出すときに、表示用のフロントマターだけを足す（既にあるキーは触らない）。
  - `title`：ファイル名先頭のタイムスタンプ（`20210419222442_` など）を除いた表示名。
    フロントマターに `Title:` があればそれを使う。
  - `modified`：Drive の最終更新日。一覧ページの日付になる。
  - `created`：ファイル名がタイムスタンプで始まる場合、その日付。
  Drive 上の元ファイルは変更しない。
- `.garden/state.json` に Drive のファイルID・パス・更新日時を記録し、変わったものだけを取得する。
- `.garden/folders.json` が Vault のルートと除外フォルダ（`.obsidian`, `template`,
  `0-playbook`, `9-archive/garden-quartz` など）を定義する。
- 全文検索は「publish」「true」を別々に拾うので誤検出が出る。`apply` がフロントマターを
  YAML として読み、`publish: true` でないものは書き出さない（state の `skipped` に記録）。

## 実行手順

1. リポジトリを用意する（`hiramoto/digital-garden` を clone、`npm ci`）。
2. Drive を検索する。次のクエリで `excludeContentSnippets: true`, `pageSize: 100`、
   `nextPageToken` がなくなるまでページを繰る。

   ```
   fullText contains 'publish: true' and mimeType = 'text/markdown'
   ```

3. `python3 scripts/garden_sync.py plan`
   - `UNKNOWN FOLDERS` が出たら、その各IDに `get_file_metadata` を呼び、もう一度 `plan`。
     （親をたどるので、出なくなるまで繰り返す）
4. `DOWNLOAD` に出た各IDに `download_file_content` を呼ぶ。結果を読む必要はない。
5. `python3 scripts/garden_sync.py apply`
   - `MISSING ATTACHMENTS` が出たら、各ファイル名で
     `title = '<名前>'` を検索して `download_file_content`、もう一度 `apply`。
   - `NOT DOWNLOADED YET` が出たら 4 をやり直す。
6. `npx quartz build` が通ることを確認する（Google Fonts 取得の警告は無視してよい）。
   失敗したら push しない。
7. `python3 scripts/garden_sync.py report` で差分を確認。
   - 差分がなければ何もしない。
   - あれば `content/` と `.garden/state.json` をコミットし、`git push origin main`。
     コミットメッセージは `sync: 追加N 更新N 削除N` とし、本文に report の一覧を入れる。

## 公開・非公開の運用

- 公開する：Obsidian でノートのフロントマターに `publish: true` を付ける。
- 非公開に戻す：`publish: true` を外す（または `false` にする）。次回の同期でサイトから消える。
- 画像：公開ノートが `![[画像.png]]` で参照している画像だけが `content/attachments/` に入る。
  参照されなくなった画像は自動で消える。
- `content/index.md`（トップページ）と `content/4-book/index.md`・`content/4-cards/index.md`
  （フォルダの表示名「読書メモ」「カード」）は同期の対象外で、手で編集する。
- 表示用フロントマターの付け方を変えたときは `plan --refresh` で全ノートを取り直す。

## 風（実生を生やす）

同期の前に、`0-playbook/心得.md`（Drive）に書かれた「風」として庭を訪れる。
コネクタではノートの中身を書き換えられないため、心得の5つの行為のうち
**「実生を生やす」だけ**を行う（言い換え・脱線・接ぎ木・蔓を張る・剪定／堆肥はしない）。

1. 実生の本数を確認する：Drive で
   `fullText contains '風が運んだ' and mimeType = 'text/markdown'` を検索し、
   見つかった各ノートを `download_file_content` → `python3 scripts/garden_sync.py show <id>` で読み、
   フロントマターの `planted` を見る。
   - 今月すでに2本ある、または直近14日以内に1本ある → 今週は生やさない。
2. 対象ノートと種子を選ぶ：リポジトリの `content/` にある公開済みノート（index.md を除く）から、
   対象ノート1本と、種子のキーワード（別の公開済みノートから拾った語）を選ぶ。
   最近の実生と同じ対象・種子は避ける。
3. 心得の「実生の規則」に従って書く。ただし置き場所とフロントマターは次のとおり：
   - 本文 100〜300字。一行目に `🌬️ この芽は風が運んだ(YYYY-MM-DD)`。
   - **公開済みノート** 2本以上への `[[リンク]]` を含める（未公開ノートへのリンクはグレーになるため）。
   - フロントマター：
     ```yaml
     ---
     title: <タイトル>
     author: 風
     planted: <YYYY-MM-DD>
     parents: ["<種子の出どころノート>", "<対象ノート>"]
     tags: [実生]
     publish: true
     ---
     ```
4. Drive の `create_file` で 4-cards（フォルダID `1uWnz03ImpJ1d9rnXB2S2bS9V9z2uh5HJ`）に作る。
   `title: "<タイトル>.md"`, `contentMimeType: "text/markdown"`,
   `disableConversionToGoogleType: true`, `textContent` に本文。既存と同名のファイルは作らない。
5. `.garden/wind-log.txt` に `日付 | 実生 | <対象ノート> | <種子>` を一行追記し、同期のコミットに含める。
   生やさなかった週は追記しない。

作った実生は、同じ回の同期の検索に出てくれば公開され、出てこなければ翌週に公開される。
