import re
from pathlib import Path

root = Path("web/.next/server")
inline: list[str] = []
external: set[str] = set()
for path in root.rglob("*.html"):
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"<script\b([^>]*)>", text, re.I):
        attrs = match.group(1)
        src = re.search(r"""src\s*=\s*["']([^"']+)["']""", attrs)
        if src:
            external.add(src.group(1))
        else:
            inline.append(str(path.relative_to(root)))

print("inline script files:", sorted(set(inline)) or "NONE")
print("--- inline bodies ---")
for path in root.rglob("*.html"):
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", text, re.I | re.S):
        attrs, body = match.group(1), match.group(2)
        if re.search(r"""src\s*=\s*["']""", attrs):
            continue
        snippet = body.strip().replace("\n", " ")[:180]
        print(path.name, "attrs=", attrs[:80], "body=", snippet)

print("script srcs:")
for src in sorted(external):
    print(" ", src)
off_origin = [src for src in external if src.startswith("http")]
print("off-origin:", off_origin or "NONE")
