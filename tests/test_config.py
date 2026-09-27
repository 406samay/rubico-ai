import yaml

import config
import sources


def _keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out.add(prefix + k)
        if isinstance(v, dict) and k != "sources":
            out |= _keys(v, prefix + k + ".")
    return out


def test_example_config_matches_defaults():
    with open(config.ROOT / "config.example.yaml", encoding="utf-8") as f:
        example = yaml.safe_load(f)
    assert _keys(example) == _keys(config.DEFAULTS)


def test_every_source_is_in_the_example_config():
    with open(config.ROOT / "config.example.yaml", encoding="utf-8") as f:
        example = yaml.safe_load(f)
    for src in sources.all_sources():
        assert src.name in example["sources"], f"add {src.name} to config.example.yaml"
        assert src.name in config.DEFAULTS["sources"]


def test_every_source_has_demo_data_that_formats():
    for src in sources.all_sources():
        text = src.format(src.demo())
        assert text.strip(), src.name


def test_nothing_personal_left_in_code():
    banned = ["samay", "sumatran", "bicester", "100.97.173", "dailybrief-506421"]
    for path in config.ROOT.rglob("*"):
        if path.suffix not in (".py", ".html", ".yaml", ".md", ".example", ".txt") and path.name != ".env.example":
            continue
        if any(part in (".git", "venv", ".venv", "data", "__pycache__") for part in path.parts):
            continue
        # The public GitHub handle in clone links is meant to be public.
        text = path.read_text(encoding="utf-8", errors="ignore").lower().replace("406samay/", "")
        for word in banned:
            if path.name == "test_config.py":
                continue
            assert word not in text, f"{word!r} found in {path}"


def test_time_parsing_handles_yaml_quirks():
    assert config.valid_time("07:30") == (7, 30)
    assert config.valid_time(450) == (7, 30)  # YAML reads bare 7:30 as 450
    assert config.valid_time("25:00") is None
    assert config.parse_time("nonsense") == (8, 0)
