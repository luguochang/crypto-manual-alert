import importlib.util
from pathlib import Path
from types import ModuleType


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "0019_ddgs_provenance.py"


class CapturingOperations:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object) -> None:
        self.statements.append(str(statement))


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0019", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ddgs_provenance_migration_is_reversible_and_targets_audit_payloads() -> None:
    migration = _load_migration()
    assert migration.revision == "0019_ddgs_provenance"
    assert migration.down_revision == "0018_progressive_events"

    upgrade_operations = CapturingOperations()
    migration.op = upgrade_operations
    migration.upgrade()
    upgrade_sql = "\n".join(upgrade_operations.statements)

    assert "pg_temp.rewrite_ddgs_provenance" in upgrade_sql
    assert "('source', 'provider', 'search_provider')" in upgrade_sql
    for table in ("web_evidence", "runs", "artifact_versions", "domain_events"):
        assert f"UPDATE app.{table}" in upgrade_sql
    assert "'duckduckgo'" in upgrade_sql
    assert "'ddgs_metasearch'" in upgrade_sql

    downgrade_operations = CapturingOperations()
    migration.op = downgrade_operations
    migration.downgrade()
    downgrade_sql = "\n".join(downgrade_operations.statements)

    assert "'ddgs_metasearch'" in downgrade_sql
    assert "'duckduckgo'" in downgrade_sql
    assert downgrade_sql.index("'ddgs_metasearch'") < downgrade_sql.index(
        "'duckduckgo'"
    )
