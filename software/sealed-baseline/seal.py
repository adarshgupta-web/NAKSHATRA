#!/usr/bin/env python3
"""Sealed survey baseline: SHA-256 manifest, hash chain across versions.

  python seal.py seal    <survey_dir> --out baseline.seal.json [--parent prev.seal.json] [--meta k=v ...]
  python seal.py verify  <survey_dir> baseline.seal.json
  python seal.py compare old.seal.json new.seal.json

A seal proves the files have not changed since sealing (integrity). It does not by
itself prove who sealed them; add a digital signature for authenticity.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys


def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(block):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def scan(root, skip=()):
    files = {}
    for base, _, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(base, n)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if rel not in skip:
                files[rel] = {"sha256": sha256_file(p), "bytes": os.path.getsize(p)}
    return dict(sorted(files.items()))


def seal(root, out, parent=None, meta=None):
    version, parent_hash = 1, None
    if parent:
        pm = json.load(open(parent))
        version, parent_hash = pm["version"] + 1, pm["seal_hash"]
    body = {"version": version, "parent_seal_hash": parent_hash,
            "sealed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "metadata": meta or {}, "files": scan(root, skip={os.path.basename(out)})}
    body["seal_hash"] = hashlib.sha256(canonical(body)).hexdigest()
    json.dump(body, open(out, "w"), indent=1)
    return body


def verify(root, manifest_path):
    m = json.load(open(manifest_path))
    claimed = m.pop("seal_hash")
    problems = []
    if hashlib.sha256(canonical(m)).hexdigest() != claimed:
        problems.append("manifest itself was modified")
    now = scan(root, skip={os.path.basename(manifest_path)})
    for f, info in m["files"].items():
        if f not in now:
            problems.append(f"missing: {f}")
        elif now[f]["sha256"] != info["sha256"]:
            problems.append(f"changed: {f}")
    problems += [f"added: {f}" for f in now if f not in m["files"]]
    return problems


def compare(a_path, b_path):
    a, b = json.load(open(a_path))["files"], json.load(open(b_path))["files"]
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "changed": sorted(f for f in set(a) & set(b) if a[f]["sha256"] != b[f]["sha256"])}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("seal"); s.add_argument("dir"); s.add_argument("--out", required=True)
    s.add_argument("--parent"); s.add_argument("--meta", nargs="*", default=[])
    v = sp.add_parser("verify"); v.add_argument("dir"); v.add_argument("manifest")
    c = sp.add_parser("compare"); c.add_argument("old"); c.add_argument("new")
    a = ap.parse_args(argv)
    if a.cmd == "seal":
        meta = dict(x.split("=", 1) for x in a.meta)
        b = seal(a.dir, a.out, a.parent, meta)
        print(f"sealed v{b['version']}  {b['seal_hash']}")
    elif a.cmd == "verify":
        p = verify(a.dir, a.manifest)
        print("OK: baseline intact" if not p else "\n".join(["TAMPER/DRIFT DETECTED:"] + p))
        return 0 if not p else 1
    else:
        print(json.dumps(compare(a.old, a.new), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
