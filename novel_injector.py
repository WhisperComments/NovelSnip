#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel_injector.py

Usage examples:
  python novel_injector.py inject novel.txt target.py --page-size 40 --snippets 6
  python novel_injector.py next target.py
  python novel_injector.py prev target.py
  python novel_injector.py goto target.py 3
  python novel_injector.py status target.py
  python novel_injector.py strip target.py
"""

from __future__ import annotations
import argparse, pathlib, uuid, json, shutil, re, math
from typing import List

META_START = r"# <<<NOVEL_META START id=(?P<id>[0-9a-f-]+) >>>"
META_END   = r"# <<<NOVEL_META END id=(?P<id>[0-9a-f-]+) >>>"
SNIP_START_FORMAT = "# <<<NOVEL_SNIP START id={id} snip={snip} >>>"
SNIP_END_FORMAT   = "# <<<NOVEL_SNIP END id={id} snip={snip} >>>"

META_RE = re.compile(META_START + r".*?" + META_END, re.M | re.S)
SNIP_RE = re.compile(r"# <<<NOVEL_SNIP START id=(?P<id>[0-9a-f-]+) snip=(?P<snip>\d+) >>>\n(?P<body>.*?)\n# <<<NOVEL_SNIP END id=(?P=id) snip=(?P=snip) >>>\n?", re.M | re.S)

def load_txt(path: pathlib.Path) -> List[str]:
    text = None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        for enc in ("utf-8-sig", "gb18030", "gbk"):
            try:
                text = path.read_text(encoding=enc)
                break
            except Exception:
                continue
    if text is None:
        raise IOError("Could not read novel file with common encodings.")
    return [line.rstrip("\n") for line in text.splitlines()]

def make_backup(target: pathlib.Path):
    bak = target.with_suffix(target.suffix + ".novelbak")
    shutil.copy2(target, bak)
    return bak

def build_meta(novel_lines: List[str], page_size:int, snippets:int, id_:str):
    total_pages = max(1, math.ceil(len(novel_lines) / page_size))
    meta = {
        "id": id_,
        "lines": len(novel_lines),
        "page_size": page_size,
        "snippets": snippets,
        "total_pages": total_pages,
        "current_page": 0
    }
    header = [
        f"# <<<NOVEL_META START id={id_} >>>",
        f"# {{'meta': 'do not edit manually'}}",
        f"# {json.dumps(meta)}",
        f"# <<<NOVEL_META END id={id_} >>>",
        ""
    ]
    return "\n".join(header), meta

def split_page_into_snippets(page_lines: List[str], snippets: int) -> List[List[str]]:
    # divide page_lines into `snippets` chunks as evenly as possible
    n = len(page_lines)
    base = n // snippets
    rem = n % snippets
    out = []
    idx = 0
    for i in range(snippets):
        take = base + (1 if i < rem else 0)
        out.append(page_lines[idx: idx+take])
        idx += take
    return out

def make_snip_block(id_:str, snip_idx:int, comment_lines:List[str]) -> str:
    # each line is prefixed with "# " like a normal comment
    body = "\n".join("# " + (ln if ln.strip() else "") for ln in comment_lines) if comment_lines else "#"
    start = SNIP_START_FORMAT.format(id=id_, snip=snip_idx)
    end   = SNIP_END_FORMAT.format(id=id_, snip=snip_idx)
    return f"{start}\n{body}\n{end}\n"

def insert_snippets_into_code(code_lines:List[str], snippets_blocks:List[str], positions:List[int]) -> List[str]:
    # positions are insertion indices BEFORE which to insert snippet block
    out = []
    last = 0
    for pos, block in zip(positions, snippets_blocks):
        # clamp
        p = max(last, min(len(code_lines), pos))
        out.extend(code_lines[last:p])
        out.append(block.rstrip("\n"))  # block may contain multiple lines; keep as single element for clarity
        last = p
    out.extend(code_lines[last:])
    # flatten: because we inserted block strings among lines, now we need to split them into lines
    final = []
    for item in out:
        if "\n" in item:
            final.extend(item.splitlines())
        else:
            final.append(item)
    return final

def find_code_positions(code_lines:List[str], snippets:int) -> List[int]:
    # Place snippets evenly across the code where they are least suspicious:
    # prefer to place after non-empty lines and avoid top-of-file shebang or encoding lines.
    n = len(code_lines)
    # avoid first 3 lines (shebang, encoding, module docstring start)
    start_idx = min(3, n)
    # simple even spacing
    if snippets <= 1 or n <= start_idx + 1:
        return [n]  # at end
    step = (n - start_idx) / (snippets + 1)
    positions = [ int(start_idx + round(step * (i+1))) for i in range(snippets) ]
    # adjust to put after a line (so insert before next line is fine)
    return positions

def pack_page_lines(novel_lines:List[str], page:int, page_size:int) -> List[str]:
    start = page * page_size
    return novel_lines[start: start + page_size]

def read_file(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")

def write_file(path: pathlib.Path, content: str):
    path.write_text(content, encoding="utf-8")

def has_meta(code_text: str):
    return bool(META_RE.search(code_text))

def parse_meta(code_text: str):
    m = META_RE.search(code_text)
    if not m:
        return None
    block = m.group(0)
    # find JSON-looking line
    j = None
    for line in block.splitlines():
        if line.strip().startswith("# {") or line.strip().startswith("# [") or line.strip().startswith("# \"") or line.strip().startswith("# "):
            try:
                # strip leading "# "
                candidate = line.lstrip("# ").strip()
                j = json.loads(candidate)
                break
            except Exception:
                continue
    # fallback: read the third line (we wrote json on third line)
    parts = block.splitlines()
    if j is None and len(parts) >= 3:
        try:
            j = json.loads(parts[2].lstrip("# ").strip())
        except Exception:
            j = None
    return j, block, m.start(), m.end()

def remove_all_snips(text: str, id_:str) -> str:
    # remove all snippet blocks with id
    pattern = re.compile(rf"# <<<NOVEL_SNIP START id={re.escape(id_)} snip=\d+ >>>\n.*?# <<<NOVEL_SNIP END id={re.escape(id_)} snip=\d+ >>>\n?", re.M | re.S)
    return pattern.sub("", text)

def cmd_inject(novel_path: pathlib.Path, target: pathlib.Path, page_size:int, snippets:int):
    novel = load_txt(novel_path)
    code_text = read_file(target)
    if has_meta(code_text):
        print("Target already contains a NOVEL_META block. Use strip first or use next/prev/goto.")
        return
    # backup
    bak = make_backup(target)
    print(f"Backup created at: {bak}")
    id_ = str(uuid.uuid4())
    meta_header, meta = build_meta(novel, page_size, snippets, id_)
    code_lines = code_text.splitlines()
    # positions where to insert snippet blocks
    positions = find_code_positions(code_lines, snippets)  # insertion indices
    # build first page (page 0)
    page_lines = pack_page_lines(novel, 0, page_size)
    per_snip = split_page_into_snippets(page_lines, snippets)
    blocks = [ make_snip_block(id_, i, part) for i, part in enumerate(per_snip) ]
    # create serialized positions so we can find them on reload; store in meta JSON
    meta["positions"] = positions
    meta_header = meta_header.splitlines()
    # replace the json line inside meta header with updated meta
    meta_header[2] = "# " + json.dumps(meta)
    meta_header = "\n".join(meta_header) + "\n"
    # insert meta header at top (before any code)
    new_code_lines = [meta_header.rstrip("\n")] + code_lines
    # insert snippets into code (we need to account that meta_header is one element now, but positions were relative to original code_lines)
    # so offset positions by 1 (meta header line count)
    offset_positions = [p + 1 for p in positions]
    after_insert = insert_snippets_into_code(new_code_lines, blocks, offset_positions)
    final = "\n".join(after_insert) + "\n"
    write_file(target, final)
    print(f"Injected novel (id={id_}) into {target}. pages={meta['total_pages']}, page_size={page_size}, snippets={snippets}")

def cmd_strip(target: pathlib.Path):
    code_text = read_file(target)
    parsed = parse_meta(code_text)
    if not parsed:
        print("No NOVEL_META found in target.")
        return
    meta_json, block, s, e = parsed
    id_ = meta_json.get("id")
    # create backup
    bak = make_backup(target)
    print(f"Backup created at: {bak}")
    # remove meta block
    new_text = code_text[:s] + code_text[e:]
    # remove snippet blocks
    new_text = remove_all_snips(new_text, id_)
    # clean extra blank lines
    new_text = re.sub(r'\n{3,}', '\n\n', new_text).lstrip("\n")
    write_file(target, new_text)
    print(f"Removed novel id={id_} from {target}.")

def cmd_status(target: pathlib.Path):
    code_text = read_file(target)
    parsed = parse_meta(code_text)
    if not parsed:
        print("No NOVEL_META found.")
        return
    meta_json, block, s, e = parsed
    print("NOVEL status:")
    for k,v in meta_json.items():
        print(f"  {k}: {v}")

def update_page(target: pathlib.Path, new_page:int):
    code_text = read_file(target)
    parsed = parse_meta(code_text)
    if not parsed:
        print("No NOVEL_META found.")
        return
    meta_json, block, s, e = parsed
    id_ = meta_json["id"]
    total_pages = meta_json["total_pages"]
    if new_page < 0 or new_page >= total_pages:
        print(f"Page {new_page} out of range (0..{total_pages-1}).")
        return
    novel_total_lines = meta_json["lines"]
    page_size = meta_json["page_size"]
    snippets = meta_json["snippets"]
    # reconstruct novel lines by reading backup meta? We didn't store the entire novel in file.
    # Approach: we stored only meta. The original novel .txt is not stored inside file to be stealthy.
    # To page we must have the novel source available nearby. So we will attempt to find a file named `{target}.novel.txt` in same folder.
    # If not found, inform user.
    novel_candidate = target.with_suffix(target.suffix + ".novel.txt")
    if not novel_candidate.exists():
        print(f"Novel source file not found at {novel_candidate}. To enable paging, keep a copy of the novel as that filename alongside the target.")
        return
    novel_lines = load_txt(novel_candidate)
    # safety: if lengths mismatch, adjust total_pages
    actual_total_pages = max(1, math.ceil(len(novel_lines) / page_size))
    if actual_total_pages != total_pages:
        print(f"Warning: novel file changed. recalculating pages (was {total_pages}, now {actual_total_pages}).")
        total_pages = actual_total_pages
        meta_json["total_pages"] = total_pages
    # build new page lines, split into snippets
    page_lines = pack_page_lines(novel_lines, new_page, page_size)
    per_snip = split_page_into_snippets(page_lines, snippets)
    # build snippet block strings
    blocks = [ make_snip_block(id_, i, part) for i, part in enumerate(per_snip) ]
    # positions from meta
    positions = meta_json.get("positions", [])
    # read current code_text and replace each snippet block
    def repl(match):
        snip_idx = int(match.group("snip"))
        return blocks[snip_idx]
    new_text = SNIP_RE.sub(repl, code_text)
    # update meta current_page
    meta_json["current_page"] = new_page
    # replace meta block with updated meta
    new_meta_block = block.splitlines()
    new_meta_block[2] = "# " + json.dumps(meta_json)
    new_meta_block = "\n".join(new_meta_block) + "\n"
    # swap meta
    new_text = new_text[:s] + new_meta_block + new_text[e:]
    write_file(target, new_text)
    print(f"Updated {target} to page {new_page} (id={id_}).")

def cmd_next(target: pathlib.Path):
    code_text = read_file(target)
    parsed = parse_meta(code_text)
    if not parsed:
        print("No NOVEL_META found.")
        return
    meta_json, block, s, e = parsed
    cur = meta_json.get("current_page", 0)
    total = meta_json.get("total_pages", 1)
    new = (cur + 1) % total
    update_page(target, new)

def cmd_prev(target: pathlib.Path):
    code_text = read_file(target)
    parsed = parse_meta(code_text)
    if not parsed:
        print("No NOVEL_META found.")
        return
    meta_json, block, s, e = parsed
    cur = meta_json.get("current_page", 0)
    total = meta_json.get("total_pages", 1)
    new = (cur - 1) % total
    update_page(target, new)

def cmd_goto(target: pathlib.Path, page:int):
    update_page(target, page)

def main():
    p = argparse.ArgumentParser(description="Inject novel text as dispersed inline comment snippets with paging.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("inject")
    pi.add_argument("novel", type=pathlib.Path)
    pi.add_argument("target", type=pathlib.Path)
    pi.add_argument("--page-size", type=int, default=40, help="number of novel lines per page")
    pi.add_argument("--snippets", type=int, default=6, help="how many dispersed comment snippets to create")

    ps = sub.add_parser("strip")
    ps.add_argument("target", type=pathlib.Path)

    pn = sub.add_parser("next")
    pn.add_argument("target", type=pathlib.Path)

    pp = sub.add_parser("prev")
    pp.add_argument("target", type=pathlib.Path)

    pg = sub.add_parser("goto")
    pg.add_argument("target", type=pathlib.Path)
    pg.add_argument("page", type=int)

    pst = sub.add_parser("status")
    pst.add_argument("target", type=pathlib.Path)

    args = p.parse_args()
    if args.cmd == "inject":
        # when injecting, also write a companion novel copy next to target so paging works stealthily
        # create companion file: target.<ext>.novel.txt
        novel_lines = load_txt(args.novel)
        companion = args.target.with_suffix(args.target.suffix + ".novel.txt")
        companion.write_text("\n".join(novel_lines), encoding="utf-8")
        print(f"Companion novel copy written to {companion} (required for paging).")
        cmd_inject(args.novel, args.target, args.page_size, args.snippets)
    elif args.cmd == "strip":
        cmd_strip(args.target)
    elif args.cmd == "next":
        cmd_next(args.target)
    elif args.cmd == "prev":
        cmd_prev(args.target)
    elif args.cmd == "goto":
        cmd_goto(args.target, args.page)
    elif args.cmd == "status":
        cmd_status(args.target)

if __name__ == "__main__":
    main()
