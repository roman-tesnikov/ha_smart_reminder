"""Keep published automation examples syntactically valid."""

import re
from pathlib import Path

import yaml


def test_all_readme_yaml_blocks_parse() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", readme, flags=re.DOTALL)

    assert blocks
    for block in blocks:
        yaml.safe_load(block)
