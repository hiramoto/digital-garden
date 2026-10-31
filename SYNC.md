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
- `.garden/state.json` に Drive のファイルID・パス・更新日時を記録し、変わったものだけを取得する。
- `.garden/folders.json` が Vault のルートと除外フォルダ（`.obsidian`, `template`,
  `garden/quartz` など）を定義する。
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
- `content/index.md` はトップページで、同期の対象外（手で編集する）。
