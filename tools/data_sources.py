"""
Gathers every switched-on data source into one plain-text blob for Claude.

Which sources run is decided by config.yaml (sources.<name>.enabled). The
sources themselves live in tools/sources/ - one file each.
"""

import config
import sources


def build_raw_data(allow_browser=True, demo=None):
    """Returns (raw_text, broken_sources).

    Every source is fetched defensively. One broken source (an expired token,
    an API outage) must degrade to a note in the text, never take down the
    whole brief - a partial brief is far more useful than no brief, and the
    broken list makes the failure visible instead of silent.
    """
    demo = config.is_demo() if demo is None else demo
    lines, broken = [], []

    for src in sources.enabled_sources():
        try:
            data = src.demo() if demo else src.fetch(allow_browser=allow_browser)
            lines.append(src.format(data))
            broken += [(part, src.fix_command()) for part in src.broken_parts(data)]
        except Exception as e:
            broken.append((f"{src.title} ({type(e).__name__}: {e})", src.fix_command()))
            lines.append(f"--- {src.title} ---\n(unavailable: {e})")
        lines.append("")

    if not lines:
        lines.append("(No data sources are switched on - see config.yaml.)")
    return "\n".join(lines), broken


def gmail_accounts():
    return config.source("gmail").get("accounts") or [] if config.source_enabled("gmail") else []


def calendar_accounts():
    return config.source("calendar").get("accounts") or [] if config.source_enabled("calendar") else []
