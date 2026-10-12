"""Vendor the curated Twemoji SVG set so clients never depend on a CDN."""
import concurrent.futures
import pathlib
import re
import urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
catalog = (root / "frontend/src/features/chat/emojiData.ts").read_text(encoding="utf-8")
emoji = {item for group in re.findall(r'items: "([^"]+)"', catalog) for item in group.split()}
target = root / "frontend/public/emoji"
target.mkdir(parents=True, exist_ok=True)
base = "https://raw.githubusercontent.com/jdecked/twemoji/v17.0.3/"

def fetch(value):
    code = "-".join(f"{ord(c):x}" for c in value if c != "\ufe0f")
    with urllib.request.urlopen(base + f"assets/svg/{code}.svg", timeout=30) as response:
        content = response.read()
    if b"<svg" not in content or b"<script" in content:
        raise ValueError(f"Invalid SVG: {code}")
    (target / f"{code}.svg").write_bytes(content)

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(fetch, emoji))
with urllib.request.urlopen(base + "LICENSE-GRAPHICS", timeout=30) as response:
    (target / "LICENSE-GRAPHICS.txt").write_bytes(response.read())
(target / "NOTICE.txt").write_text(
    "Twemoji graphics v17.0.3\nCopyright Twitter, Inc. and other contributors.\n"
    "Source: https://github.com/jdecked/twemoji/tree/v17.0.3\n"
    "Licensed under Creative Commons Attribution 4.0 International.\n"
    "https://creativecommons.org/licenses/by/4.0/\n"
    "Unmodified SVG graphics; curated subset distributed locally.\n", encoding="utf-8")
print(f"Vendored {len(emoji)} emoji SVGs with license and attribution.")
