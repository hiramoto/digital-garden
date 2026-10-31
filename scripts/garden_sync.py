#!/usr/bin/env python3
"""Sync `publish: true` notes from the Obsidian vault on Google Drive into content/.

The Drive connector is only reachable as tool calls (search_files,
get_file_metadata, download_file_content), so this script never talks to
Drive itself. Instead it reads the results of those calls from the Claude
session transcripts (~/.claude/projects/**/*.jsonl and tool-results/*.txt)
and copies file contents byte-for-byte from the base64 the connector
returned. Nothing is retyped by the model.

Subcommands (see SYNC.md for the full run procedure):
  plan    decide which notes to download / delete, and which folders are unknown
  apply   write downloaded notes and attachments into content/, prune, update state
  report  print a short summary of what changed in content/ (git based)
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CONTENT = REPO / "content"
ATTACH_DIR = CONTENT / "attachments"
STATE_DIR = REPO / ".garden"
STATE_FILE = STATE_DIR / "state.json"
FOLDERS_FILE = STATE_DIR / "folders.json"
PLAN_FILE = STATE_DIR / "plan.json"

# Files written by hand in content/ (not synced from the vault) are never pruned.
MANAGED_MARK = "synced"


# ---------------------------------------------------------------- transcript

SAVED_RE = re.compile(r"(/\S+?tool-results/\S+?\.txt)")


def _iter_tool_payloads():
    """Yield (tool_input, payload) for every JSON object a tool returned, in order.

    Large results are spilled by the harness into tool-results/*.txt and the
    transcript only holds a pointer; those are followed.
    """
    files = glob.glob(os.path.expanduser("~/.claude/projects/**/*.jsonl"), recursive=True)
    files.sort(key=lambda p: os.path.getmtime(p))
    for path in files:
        inputs: dict[str, dict] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if '"tool_use"' not in line and '"tool_result"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        inputs[block.get("id")] = {"name": block.get("name", ""), **(block.get("input") or {})}
                        continue
                    if block.get("type") != "tool_result":
                        continue
                    tool_input = inputs.get(block.get("tool_use_id"), {})
                    inner = block.get("content")
                    texts = [inner] if isinstance(inner, str) else [
                        b.get("text", "") for b in (inner or []) if isinstance(b, dict)]
                    for t in texts:
                        t = t.strip()
                        if not t.startswith("{"):
                            m = SAVED_RE.search(t)
                            if not m or not os.path.exists(m.group(1)):
                                continue
                            t = Path(m.group(1)).read_text(encoding="utf-8").strip()
                        try:
                            yield tool_input, json.loads(t)
                        except Exception:
                            pass


def collect():
    """Return (metadata by id, downloads by id, ids hit by a publish search)."""
    meta: dict[str, dict] = {}
    downloads: dict[str, dict] = {}
    publish_hits: set[str] = set()
    for tool_input, obj in _iter_tool_payloads():
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("files"), list):
            is_publish_search = "publish: true" in str(tool_input.get("query", ""))
            for f in obj["files"]:
                if isinstance(f, dict) and f.get("id"):
                    meta[f["id"]] = {**meta.get(f["id"], {}), **f}
                    if is_publish_search:
                        publish_hits.add(f["id"])
        elif obj.get("id") and "content" in obj and "mimeType" in obj:
            downloads[obj["id"]] = obj
        elif obj.get("id") and obj.get("mimeType"):
            meta[obj["id"]] = {**meta.get(obj["id"], {}), **obj}
    return meta, downloads, publish_hits


# ---------------------------------------------------------------- state

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def folder_path(folder_id: str, folders: dict, meta: dict, unknown: set):
    """Vault-relative folder path for folder_id, or None if outside/excluded."""
    chain = []
    cur = folder_id
    for _ in range(30):
        if cur in folders["exclude"]:
            return None
        if cur == folders["root"]:
            return "/".join(reversed(chain))
        if cur in folders["paths"]:
            base = folders["paths"][cur]
            return "/".join([base] + list(reversed(chain))) if chain else base
        m = meta.get(cur)
        if not m:
            unknown.add(cur)
            return None
        if m.get("mimeType") != "application/vnd.google-apps.folder":
            return None
        chain.append(m["title"])
        parent = m.get("parentId")
        if not parent:
            return None  # reached the top of Drive without passing the vault root
        cur = parent
    return None


def is_published(text: str) -> bool:
    m = re.match(r"^﻿?---\r?\n(.*?)\r?\n---\s*(\r?\n|$)", text, re.S)
    if not m:
        return False
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return False
    if not isinstance(fm, dict):
        return False
    v = fm.get("publish")
    return v is True or (isinstance(v, str) and v.strip().lower() == "true")


# Leading timestamp in Obsidian note names: 20210419222442_ / 202312302146 / 20230111220157 etc.
STAMP_RE = re.compile(r"^(?P<stamp>\d{12}(?:\d{2})?)(?:[ _\-]+|$)")


def display_title(stem: str, fm: dict) -> str:
    for key in ("title", "Title"):
        v = fm.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    m = STAMP_RE.match(stem)
    rest = stem[m.end():].strip() if m else stem
    return rest or stem


def decorate(text: str, rel_path: str, modified_time: str | None) -> str:
    """Add display-only frontmatter (title / created / modified) to the synced copy.

    The note body and existing keys are left untouched; keys are only added
    when absent, right after the opening '---'. Drive is never modified.
    """
    m = re.match(r"^(﻿?---\r?\n)(.*?)(\r?\n---\s*(?:\r?\n|$))", text, re.S)
    if not m:
        return text
    try:
        fm = yaml.safe_load(m.group(2)) or {}
    except Exception:
        return text
    if not isinstance(fm, dict):
        return text
    stem = Path(rel_path).stem
    add = []
    if "title" not in fm:
        title = display_title(stem, fm)
        if title != stem:
            add.append(f"title: {json.dumps(title, ensure_ascii=False)}")
    if "modified" not in fm and modified_time:
        add.append(f"modified: {modified_time[:10]}")
    stamp = STAMP_RE.match(stem)
    if "created" not in fm and stamp:
        s = stamp.group("stamp")
        add.append(f"created: {s[0:4]}-{s[4:6]}-{s[6:8]}")
    if not add:
        return text
    nl = "\r\n" if m.group(1).endswith("\r\n") else "\n"
    return m.group(1) + nl.join(add) + nl + text[m.end(1):]


# ---------------------------------------------------------------- plan

def cmd_plan(args):
    folders = load_json(FOLDERS_FILE, None)
    if folders is None:
        sys.exit(f"missing {FOLDERS_FILE}")
    state = load_json(STATE_FILE, {})
    for k in ("notes", "attachments", "skipped"):
        state.setdefault(k, {})
    meta, _, publish_hits = collect()
    if not publish_hits:
        sys.exit("no publish search found in this session — run the Drive search first")

    unknown: set[str] = set()
    candidates = {}
    for fid in publish_hits:
        m = meta[fid]
        if not m.get("title", "").endswith(".md"):
            continue
        parent = m.get("parentId")
        if not parent:
            continue
        rel_dir = folder_path(parent, folders, meta, unknown)
        if rel_dir is None:
            continue
        candidates[fid] = {
            "path": f"{rel_dir}/{m['title']}" if rel_dir else m["title"],
            "modifiedTime": m.get("modifiedTime"),
            "title": m["title"],
        }

    # Two Drive files mapping to one path: keep the newest, report the rest.
    by_path: dict[str, str] = {}
    for fid in sorted(candidates, key=lambda f: candidates[f]["modifiedTime"] or ""):
        prev = by_path.get(candidates[fid]["path"])
        if prev:
            print("DUPLICATE PATH (older one ignored):", candidates[fid]["path"], prev)
            candidates.pop(prev)
        by_path[candidates[fid]["path"]] = fid

    download, keep, delete = [], [], []
    for fid, c in candidates.items():
        old = state["notes"].get(fid) or state["skipped"].get(fid)
        if (not args.refresh and old and old.get("modifiedTime") == c["modifiedTime"]
                and old.get("path") == c["path"]):
            keep.append(fid)
        else:
            download.append(fid)
    for fid in list(state["skipped"]):
        if fid not in candidates:
            state["skipped"].pop(fid)
            save_json(STATE_FILE, state)
    if not unknown:
        for fid, old in state["notes"].items():
            if fid not in candidates:
                delete.append(fid)

    plan = {"download": download, "keep": keep, "delete": delete,
            "unknown_folders": sorted(unknown), "candidates": candidates}
    save_json(PLAN_FILE, plan)
    print(f"candidates: {len(candidates)}  download: {len(download)}  unchanged: {len(keep)}  delete: {len(delete)}")
    if unknown:
        print("UNKNOWN FOLDERS — call get_file_metadata on each id, then run plan again:")
        for u in sorted(unknown):
            print("  ", u)
    for fid in download:
        print("DOWNLOAD", fid, candidates[fid]["path"])
    for fid in delete:
        print("DELETE  ", fid, state["notes"][fid].get("path"))


# ---------------------------------------------------------------- apply

EMBED_WIKI = re.compile(r"!\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
EMBED_MD = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
ATTACH_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf", ".bmp", ".avif", ".mp4", ".mp3", ".m4a", ".webm"}


def referenced_attachments() -> set[str]:
    names = set()
    for md in CONTENT.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in EMBED_WIKI.finditer(text):
            names.add(Path(m.group(1).strip()).name)
        for m in EMBED_MD.finditer(text):
            target = m.group(1)
            if "://" in target:
                continue
            names.add(Path(target).name.replace("%20", " "))
    return {n for n in names if Path(n).suffix.lower() in ATTACH_EXT}


def safe_join(base: Path, rel: str) -> Path:
    p = (base / rel).resolve()
    if base.resolve() not in p.parents and p != base.resolve():
        raise ValueError(f"path escapes content/: {rel}")
    return p


def cmd_apply(args):
    plan = load_json(PLAN_FILE, None)
    if plan is None:
        sys.exit("run plan first")
    state = load_json(STATE_FILE, {})
    for k in ("notes", "attachments", "skipped"):
        state.setdefault(k, {})
    meta, downloads, _ = collect()

    written, skipped, missing_dl = [], [], []
    for fid in plan["download"]:
        c = plan["candidates"][fid]
        d = downloads.get(fid)
        if not d:
            missing_dl.append(fid)
            continue
        raw = base64.b64decode(d["content"])
        text = raw.decode("utf-8", errors="replace")
        old = state["notes"].get(fid)
        if old and old.get("path") and old["path"] != c["path"]:
            oldp = safe_join(CONTENT, old["path"])
            if oldp.exists():
                oldp.unlink()
        if not is_published(text):
            # Matched the search text but frontmatter says otherwise: keep it out.
            if old and old.get("path"):
                p = safe_join(CONTENT, old["path"])
                if p.exists():
                    p.unlink()
            state["notes"].pop(fid, None)
            state["skipped"][fid] = {"path": c["path"], "modifiedTime": c["modifiedTime"]}
            skipped.append(c["path"])
            continue
        dest = safe_join(CONTENT, c["path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(decorate(text, c["path"], c["modifiedTime"]), encoding="utf-8", newline="")
        state["notes"][fid] = {"path": c["path"], "modifiedTime": c["modifiedTime"], "status": MANAGED_MARK}
        state["skipped"].pop(fid, None)
        written.append(c["path"])

    deleted = []
    for fid in plan["delete"]:
        old = state["notes"].pop(fid, None)
        if old and old.get("path"):
            p = safe_join(CONTENT, old["path"])
            if p.exists():
                p.unlink()
                deleted.append(old["path"])

    # Attachments: write any downloaded non-markdown file whose name is referenced.
    refs = referenced_attachments()
    for fid, d in downloads.items():
        title = d.get("title", "")
        if title in refs and not title.endswith(".md"):
            dest = safe_join(ATTACH_DIR, title)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(base64.b64decode(d["content"]))
            state["attachments"][fid] = {"path": f"attachments/{title}",
                                         "modifiedTime": meta.get(fid, {}).get("modifiedTime")}
    # Prune attachments nobody references any more.
    for fid, a in list(state["attachments"].items()):
        if Path(a["path"]).name not in refs:
            p = safe_join(CONTENT, a["path"])
            if p.exists():
                p.unlink()
            state["attachments"].pop(fid)
    present = {Path(a["path"]).name for a in state["attachments"].values()}
    missing_attach = sorted(refs - present)

    # Remove empty folders left behind.
    for d in sorted(CONTENT.rglob("*"), key=lambda p: -len(p.parts)):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    save_json(STATE_FILE, state)
    print(f"written: {len(written)}  deleted: {len(deleted)}  not-published: {len(skipped)}")
    for p in skipped:
        print("NOT PUBLISHED (frontmatter)", p)
    if missing_dl:
        print("NOT DOWNLOADED YET — download_file_content these ids, then apply again:")
        for fid in missing_dl:
            print("  ", fid, plan["candidates"][fid]["path"])
    if missing_attach:
        print("MISSING ATTACHMENTS — search Drive by title, download, then apply again:")
        for n in missing_attach:
            print("  ", n)


# ---------------------------------------------------------------- report

def cmd_report(args):
    import subprocess
    out = subprocess.run(["git", "status", "--porcelain", "-uall", "--", "content"],
                         cwd=REPO, capture_output=True, text=True).stdout
    added, modified, removed = [], [], []
    for line in out.splitlines():
        code, path = line[:2], line[3:].strip().strip('"')
        path = path.encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace") if "\\" in path else path
        if "?" in code or "A" in code:
            added.append(path)
        elif "D" in code:
            removed.append(path)
        else:
            modified.append(path)
    for label, items in (("追加", added), ("更新", modified), ("削除", removed)):
        print(f"{label}: {len(items)}")
        for i in items:
            print("  -", i.removeprefix("content/"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--refresh", action="store_true",
                   help="re-download every published note (e.g. after changing decorate())")
    sub.add_parser("apply")
    sub.add_parser("report")
    args = ap.parse_args()
    if args.cmd == "plan":
        cmd_plan(args)
    elif args.cmd == "apply":
        cmd_apply(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    main()
