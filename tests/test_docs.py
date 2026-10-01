"""The pages people read on GitHub must not point at things that don't exist."""

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md"))]

LINK = re.compile(r"""(?:\]\(|src=["'])([^)"'\s]+)""")


def local_targets(page):
    for target in LINK.findall(page.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        yield target


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_local_link_and_image_exists(page):
    for target in local_targets(page):
        path = unquote(target.split("#", 1)[0])
        if not path:
            continue
        assert (page.parent / path).exists(), f"{page.name} links to {target}, which doesn't exist"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_heading_link_points_at_a_real_heading(page):
    text = page.read_text(encoding="utf-8")
    anchors = set()
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, flags=re.M):
        slug = re.sub(r"[^\w\s-]", "", heading.lower().strip()).replace(" ", "-")
        anchors.add(slug)
    for target in re.findall(r"\]\(#([^)]+)\)", text):
        assert target in anchors, f"{page.name} links to #{target}, but no heading makes that address"


def test_start_files_named_in_the_readme_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name in ("start.bat", "start.command", "start.sh"):
        assert name in readme, f"README should explain {name}"
        assert (ROOT / name).exists()
