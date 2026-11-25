#!/usr/bin/env python3
"""Count lines of code across cloned repositories and render SVG cards.

Reads every repository checked out under --repos, runs tokei over the whole
tree once, then writes:

  assets/languages-light.svg
  assets/languages-dark.svg
  assets/languages.json

The SVGs are committed by the GitHub Action and embedded in the profile
README, so the numbers refresh without any third-party stats service.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Formats that are prose or machine data rather than source code. Excluding
# them keeps the language share about code, not about generated JSON.
NON_CODE = {
    "Markdown",
    "Text",
    "JSON",
    "YAML",
    "TOML",
    "CSV",
    "TSV",
    "Ignore List",
    "License",
    "Browserslist",
    "EditorConfig",
    "Git Config",
    "GitIgnore",
    "Diff",
    "reStructuredText",
    "AsciiDoc",
    "Org",
}

# GitHub linguist colours for the languages most likely to show up.
COLORS = {
    "Rust": "#dea584",
    "TypeScript": "#3178c6",
    "TSX": "#3178c6",
    "JavaScript": "#f1e05a",
    "JSX": "#f1e05a",
    "Python": "#3572a5",
    "Go": "#00add8",
    "C": "#555555",
    "C Header": "#555555",
    "C++": "#f34b7d",
    "C++ Header": "#f34b7d",
    "C#": "#178600",
    "Lua": "#000080",
    "Shell": "#89e051",
    "BASH": "#89e051",
    "Zsh": "#89e051",
    "Fish": "#4aae47",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "SCSS": "#c6538c",
    "Sass": "#a53b70",
    "Svelte": "#ff3e00",
    "Vue": "#41b883",
    "Astro": "#ff5a03",
    "Dart": "#00b4ab",
    "Java": "#b07219",
    "Kotlin": "#a97bff",
    "Swift": "#f05138",
    "Zig": "#ec915c",
    "Nix": "#7e7eff",
    "GLSL": "#5686a5",
    "HLSL": "#aace60",
    "Assembly": "#6e4c13",
    "Makefile": "#427819",
    "Dockerfile": "#384d54",
    "Elixir": "#6e4a7e",
    "Haskell": "#5e5086",
    "Ruby": "#701516",
    "PHP": "#4f5d95",
    "PowerShell": "#012456",
    "Batch": "#c1f12e",
    "QML": "#44a51c",
    "Objective-C": "#438eff",
    "Solidity": "#aa6746",
    "Verilog": "#b2b7f8",
    "CMake": "#da3434",
    "Meson": "#007800",
    "R": "#198ce7",
    "Julia": "#a270ba",
    "Scala": "#c22d40",
    "OCaml": "#ef7a08",
    "Erlang": "#b83998",
    "Clojure": "#db5855",
    "Vim Script": "#199f4b",
    "VimL": "#199f4b",
    "GDScript": "#355570",
    "Racket": "#3c5caa",
    "D": "#ba595e",
    "Vala": "#a56de2",
    "Nim": "#ffc200",
    "Crystal": "#000100",
    "Groovy": "#4298b8",
    "MATLAB": "#e16737",
    "TeX": "#3d6117",
    "Java Properties": "#2a6277",
    "Just": "#384d54",
    "HCL": "#844fba",
}

FALLBACK_COLORS = [
    "#7b68ee", "#2f81f7", "#3fb950", "#d29922", "#db61a2",
    "#a371f7", "#39c5cf", "#f0883e", "#8b949e",
]


def run_tokei(paths: list[str]) -> dict:
    cmd = ["tokei", "--output", "json", "--hidden", *paths]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not proc.stdout.strip():
        sys.exit(f"tokei produced no output:\n{proc.stderr.strip()}")
    return json.loads(proc.stdout)


def color_for(name: str, index: int) -> str:
    if name in COLORS:
        return COLORS[name]
    return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt(n: int) -> str:
    return f"{n:,}"


def build_payload(report: dict, repo_count: int) -> dict:
    langs = []
    for name, data in report.items():
        if name in ("Total",):
            continue
        code = data.get("code", 0)
        if code <= 0 or name in NON_CODE:
            continue
        langs.append(
            {
                "name": name,
                "code": code,
                "comments": data.get("comments", 0),
                "blanks": data.get("blanks", 0),
                "files": len(data.get("reports", [])),
            }
        )

    langs.sort(key=lambda item: item["code"], reverse=True)
    total = sum(item["code"] for item in langs)
    for item in langs:
        item["percent"] = (item["code"] / total * 100) if total else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "repositories": repo_count,
        "languages_counted": len(langs),
        "total_code": total,
        "languages": langs,
    }


def render(payload: dict, theme: str, top: int) -> str:
    if theme == "dark":
        bg, border = "#0d1117", "#30363d"
        text, muted = "#e6edf3", "#8b949e"
        track, rule = "#21262d", "#21262d"
    else:
        bg, border = "#ffffff", "#d0d7de"
        text, muted = "#1f2328", "#656d76"
        track, rule = "#eaeef2", "#d8dee4"

    width = 495
    pad = 24
    row_h = 27
    header_h = 62
    footer_h = 34

    ranked = payload["languages"][:top]
    rest = payload["languages"][top:]
    rows = list(ranked)
    if rest:
        rows.append(
            {
                "name": f"Other ({len(rest)} langs)",
                "code": sum(item["code"] for item in rest),
                "percent": sum(item["percent"] for item in rest),
                "color": muted,
            }
        )
    for index, item in enumerate(rows):
        item.setdefault("color", color_for(item["name"], index))

    height = header_h + row_h * len(rows) + footer_h

    bar_x, bar_w = 200, 170
    pct_x = width - pad
    loc_x = width - pad - 58

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Lines of code by language">',
        "<style>",
        "  text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', "
        "'Noto Sans', Helvetica, Arial, sans-serif; }",
        "  .num { font-variant-numeric: tabular-nums; }",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" '
        f'fill="{bg}" stroke="{border}"/>',
        f'<text x="{pad}" y="34" font-size="15" font-weight="600" fill="{text}">'
        "Code by language</text>",
        f'<text x="{pct_x}" y="34" font-size="14" font-weight="600" fill="{text}" '
        f'text-anchor="end" class="num">{fmt(payload["total_code"])} LOC</text>',
        f'<line x1="{pad}" y1="46" x2="{width - pad}" y2="46" stroke="{rule}"/>',
    ]

    y = header_h + 4
    for item in rows:
        pct = item["percent"]
        fill_w = max(3.0, bar_w * pct / 100.0)
        out.append(
            f'<circle cx="{pad + 4}" cy="{y - 4}" r="4.5" fill="{item["color"]}"/>'
        )
        out.append(
            f'<text x="{pad + 16}" y="{y}" font-size="13" fill="{text}">'
            f'{esc(item["name"])}</text>'
        )
        out.append(
            f'<rect x="{bar_x}" y="{y - 10}" width="{bar_w}" height="7" rx="3.5" '
            f'fill="{track}"/>'
        )
        out.append(
            f'<rect x="{bar_x}" y="{y - 10}" width="{fill_w:.1f}" height="7" rx="3.5" '
            f'fill="{item["color"]}"/>'
        )
        out.append(
            f'<text x="{loc_x}" y="{y}" font-size="12" fill="{muted}" '
            f'text-anchor="end" class="num">{fmt(item["code"])}</text>'
        )
        out.append(
            f'<text x="{pct_x}" y="{y}" font-size="12" fill="{text}" '
            f'text-anchor="end" class="num">{pct:.1f}%</text>'
        )
        y += row_h

    y += 4
    out.append(f'<line x1="{pad}" y1="{y - 12}" x2="{width - pad}" y2="{y - 12}" stroke="{rule}"/>')
    out.append(
        f'<text x="{pad}" y="{y + 6}" font-size="11" fill="{muted}">'
        f'{payload["repositories"]} repositories &#183; '
        f'{payload["languages_counted"]} languages &#183; source code only</text>'
    )
    out.append(
        f'<text x="{pct_x}" y="{y + 6}" font-size="11" fill="{muted}" '
        f'text-anchor="end">updated {esc(payload["generated_at"])}</text>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos", default="repos", help="directory of cloned repos")
    parser.add_argument("--out", default="assets", help="output directory")
    parser.add_argument("--top", type=int, default=8, help="languages to list")
    args = parser.parse_args()

    repos_dir = Path(args.repos)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not repos_dir.is_dir():
        sys.exit(f"no such directory: {repos_dir}")

    targets = [str(p) for p in sorted(repos_dir.iterdir()) if p.is_dir()]
    if not targets:
        sys.exit(f"no repositories found under {repos_dir}")

    payload = build_payload(run_tokei(targets), len(targets))
    (out_dir / "languages.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "languages-light.svg").write_text(
        render(payload, "light", args.top), encoding="utf-8"
    )
    (out_dir / "languages-dark.svg").write_text(
        render(payload, "dark", args.top), encoding="utf-8"
    )
    print(
        f"{payload['repositories']} repos, {payload['languages_counted']} languages, "
        f"{payload['total_code']:,} code lines"
    )
    for item in payload["languages"][: args.top]:
        print(f"  {item['name']:<16} {item['code']:>10,}  {item['percent']:5.1f}%")


if __name__ == "__main__":
    main()
