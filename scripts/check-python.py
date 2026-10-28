import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "src" / "agent_plugin").rglob("*.py"))
for source in SOURCES:
    ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
print(f"Python syntax OK: {len(SOURCES)} files")
