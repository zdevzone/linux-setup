#!/usr/bin/env python3
"""Update explicitly named tools to their latest stable GitHub releases."""
import argparse
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
path = root / "tools.lock.json"
lock = json.loads(path.read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("tools", nargs="+", choices=list(lock["tools"]))
args = parser.parse_args()

for name in args.tools:
    item = lock["tools"][name]
    repo = item["repository"].removeprefix("https://github.com/")
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={"User-Agent": "linux-setup/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        release = json.load(response)
    old, new = item["version"], release["tag_name"]
    assets = {asset["name"]: asset for asset in release["assets"]}
    for key, current in item["platforms"].items():
        filename = current["name"]
        if old in filename:
            filename = filename.replace(old, new)
        elif old.removeprefix("v") in filename:
            filename = filename.replace(old.removeprefix("v"), new.removeprefix("v"))
        asset = assets.get(filename)
        if not asset or not (asset.get("digest") or "").startswith("sha256:"):
            raise SystemExit(f"No checksummed asset {filename} for {name}/{key}; lockfile unchanged.")
        item["platforms"][key] = {"name": filename, "url": asset["browser_download_url"], "sha256": asset["digest"].split(":", 1)[1]}
    item["version"] = new
    print(f"{name}: {old} -> {new}")

temporary = path.with_suffix(".json.tmp")
temporary.write_text(json.dumps(lock, indent=2) + "\n")
temporary.replace(path)
print("Updated tools.lock.json. Review the diff before installing.")
