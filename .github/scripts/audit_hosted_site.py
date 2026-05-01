#!/usr/bin/env python3
"""Public-site preflight and live smoke audit for DoorCodes GitHub Pages."""

from __future__ import annotations

import argparse
import html.parser
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://doorcodesapp.com"
APP_STORE_URL = "https://apps.apple.com/us/app/doorcodes-vault/id6761863570"
CORE_PAGES = {
    "index.html": f"{BASE_URL}/",
    "faq.html": f"{BASE_URL}/faq.html",
    "whats-new.html": f"{BASE_URL}/whats-new.html",
    "press.html": f"{BASE_URL}/press.html",
    "support.html": f"{BASE_URL}/support.html",
    "privacy.html": f"{BASE_URL}/privacy.html",
}
REQUIRED_FILES = [
    ".nojekyll",
    "CNAME",
    "robots.txt",
    "sitemap.xml",
    "site.css",
    "assets/download-on-app-store.svg",
    "assets/doorcodes-social-preview.png",
    "media-kit/doorcodes-media-kit.zip",
]
FORBIDDEN = {
    "Figma capture script": r"mcp\.figma\.com/mcp/html-to-design/capture\.js|figmacapture",
    "legacy custom App Store CTA": r"app-store-cta|store-icon",
    "automatic door-opening claim": r"automatically\s+(opens?|unlocks?)\s+doors?|one\s+tap\s+(opens?|unlocks?)",
}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


class Parser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []
        self.images: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []
        self.meta: dict[tuple[str, str], str] = {}
        self.visible_text: list[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignore_depth += 1
        values = {key: value or "" for key, value in attrs}
        if values.get("href"):
            self.refs.append(values["href"])
        if values.get("src"):
            self.refs.append(values["src"])
        if tag == "img":
            self.images.append(values)
        if tag == "a":
            self.anchors.append(values)
        if tag == "meta" and values.get("property"):
            self.meta[("property", values["property"])] = values.get("content", "")
        if tag == "link" and values.get("rel") == "canonical":
            self.meta[("link", "canonical")] = values.get("href", "")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignore_depth:
            self._ignore_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text and not self._ignore_depth:
            self.visible_text.append(text)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse(path: Path) -> Parser:
    parser = Parser()
    parser.feed(read(path))
    return parser


def add(checks: list[Check], name: str, ok: bool, detail: str = "") -> None:
    checks.append(Check(name, ok, detail if not ok else ""))


def external(ref: str) -> bool:
    return ref.startswith(("http://", "https://", "mailto:", "tel:", "#", "data:", "javascript:", "//"))


def check_required(root: Path, checks: list[Check]) -> None:
    missing = [path for path in REQUIRED_FILES if not (root / path).exists()]
    add(checks, "required files exist", not missing, ", ".join(missing))
    cname = read(root / "CNAME").strip() if (root / "CNAME").exists() else ""
    add(checks, "CNAME is doorcodesapp.com", cname == "doorcodesapp.com", cname)
    robots = read(root / "robots.txt") if (root / "robots.txt").exists() else ""
    add(checks, "robots references production sitemap", f"{BASE_URL}/sitemap.xml" in robots)
    sitemap = read(root / "sitemap.xml") if (root / "sitemap.xml").exists() else ""
    missing_urls = [url for url in CORE_PAGES.values() if url not in sitemap]
    add(checks, "sitemap includes core pages", not missing_urls, ", ".join(missing_urls))


def check_html(root: Path, checks: list[Check]) -> None:
    missing_refs: list[str] = []
    meta_failures: list[str] = []
    badge_failures: list[str] = []
    visible = []
    for page, expected_url in CORE_PAGES.items():
        path = root / page
        parser = parse(path)
        visible.extend(parser.visible_text)
        if parser.meta.get(("link", "canonical")) != expected_url:
            meta_failures.append(f"{page} canonical")
        if parser.meta.get(("property", "og:url")) != expected_url:
            meta_failures.append(f"{page} og:url")
        app_links = [anchor for anchor in parser.anchors if anchor.get("href") == APP_STORE_URL]
        badge_count = sum(
            1
            for image in parser.images
            if image.get("src") == "assets/download-on-app-store.svg"
            and image.get("alt") == "Download on the App Store"
        )
        if app_links and badge_count < 1:
            badge_failures.append(page)
        for ref in parser.refs:
            if external(ref):
                continue
            local = urllib.parse.unquote(urllib.parse.urlparse(ref).path)
            target = (path.parent / local).resolve() if not local.startswith("/") else (root / local.lstrip("/")).resolve()
            if ref.endswith("/") or target.is_dir():
                target = target / "index.html"
            if not target.exists():
                missing_refs.append(f"{page}->{ref}")
    add(checks, "local references resolve", not missing_refs, "; ".join(missing_refs[:8]))
    add(checks, "canonical and og:url are production URLs", not meta_failures, ", ".join(meta_failures))
    add(checks, "official App Store badge is used for App Store CTAs", not badge_failures, ", ".join(badge_failures))

    visible_text = "\n".join(visible)
    expected_terms = ["iPhone", "iPad", "Face ID", "Touch ID", "iCloud", "App Store", "Secure Reveal"]
    missing_terms = [term for term in expected_terms if term not in visible_text]
    add(checks, "Apple/product names use expected casing", not missing_terms, ", ".join(missing_terms))
    lower_drift = re.findall(r"\b(?:iphone|ipad|icloud)\b", re.sub(r"\biPhone\b|\biPad\b|\biCloud\b", "", visible_text))
    add(checks, "no obvious lowercase Apple product-name drift", not lower_drift, ", ".join(sorted(set(lower_drift))))


def check_patterns(root: Path, checks: list[Check]) -> None:
    text_files = [*root.rglob("*.html"), root / "site.css", root / "README.md"]
    for label, pattern in FORBIDDEN.items():
        matches = []
        regex = re.compile(pattern, re.IGNORECASE)
        for path in text_files:
            if path.exists() and regex.search(read(path)):
                matches.append(str(path.relative_to(root)))
        add(checks, f"no {label}", not matches, ", ".join(matches))


def check_zip(root: Path, checks: list[Check]) -> None:
    expected = {"doorcodes-press-release.md", "doorcodes-one-sheet.pdf", "doorcodes-wordmark.svg"}
    try:
        with zipfile.ZipFile(root / "media-kit" / "doorcodes-media-kit.zip") as archive:
            missing = sorted(expected - set(archive.namelist()))
        add(checks, "media kit ZIP is readable", not missing, ", ".join(missing))
    except Exception as error:  # noqa: BLE001
        add(checks, "media kit ZIP is readable", False, str(error))


def check_live(checks: list[Check]) -> None:
    urls = [
        *CORE_PAGES.values(),
        APP_STORE_URL,
        f"{BASE_URL}/media-kit/doorcodes-media-kit.zip",
        f"{BASE_URL}/assets/download-on-app-store.svg",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "DoorCodesPagesAudit/1.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                add(checks, f"live URL responds: {url}", 200 <= response.status < 400, f"HTTP {response.status}")
        except urllib.error.HTTPError as error:
            add(checks, f"live URL responds: {url}", False, f"HTTP {error.code}")
        except Exception as error:  # noqa: BLE001
            add(checks, f"live URL responds: {url}", False, str(error))


def run(root: Path, live: bool) -> list[Check]:
    checks: list[Check] = []
    add(checks, "hosted root exists", root.exists(), str(root))
    if root.exists():
        check_required(root, checks)
        check_html(root, checks)
        check_patterns(root, checks)
        check_zip(root, checks)
    if live:
        check_live(checks)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hosted-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    checks = run(args.hosted_root.resolve(), args.live)
    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'}: {check.name}" + (f" - {check.detail}" if check.detail else ""))
    failed = [check for check in checks if not check.ok]
    print()
    if failed:
        print(f"DoorCodes Pages audit failed: {len(failed)} issue(s).")
        return 1
    print(f"DoorCodes Pages audit passed: {len(checks)} checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
