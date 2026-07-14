"""Keep published automation examples syntactically valid."""

import re
from pathlib import Path

import yaml


def test_all_readme_yaml_blocks_parse() -> None:
    for filename in ("README.md", "README_RU.md"):
        readme = Path(filename).read_text(encoding="utf-8")
        blocks = re.findall(r"```yaml\n(.*?)```", readme, flags=re.DOTALL)

        assert blocks, f"{filename} must contain YAML examples"
        for block in blocks:
            yaml.safe_load(block)


def test_readme_language_links_are_reciprocal() -> None:
    english = Path("README.md").read_text(encoding="utf-8")
    russian = Path("README_RU.md").read_text(encoding="utf-8")

    assert english.startswith("> 🇷🇺 [Русская версия документации](README_RU.md)")
    assert russian.startswith("> 🇬🇧 [English version](README.md)")
