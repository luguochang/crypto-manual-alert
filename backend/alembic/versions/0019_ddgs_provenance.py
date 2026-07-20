"""Correct DDGS metasearch provider provenance in persisted Product records."""

from alembic import op
import sqlalchemy as sa


revision = "0019_ddgs_provenance"
down_revision = "0018_progressive_events"
branch_labels = None
depends_on = None

PRODUCT_SCHEMA = "app"
LEGACY_PROVIDER = "duckduckgo"
DDGS_PROVIDER = "ddgs_metasearch"


def _rewrite_provenance(old_value: str, new_value: str) -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION pg_temp.rewrite_ddgs_provenance(
                document jsonb,
                old_value text,
                new_value text
            ) RETURNS jsonb
            LANGUAGE plpgsql
            IMMUTABLE
            STRICT
            AS $$
            DECLARE
                entry_key text;
                entry_value jsonb;
                rewritten jsonb;
            BEGIN
                IF jsonb_typeof(document) = 'object' THEN
                    rewritten := '{}'::jsonb;
                    FOR entry_key, entry_value IN
                        SELECT key, value FROM jsonb_each(document)
                    LOOP
                        rewritten := rewritten || jsonb_build_object(
                            entry_key,
                            CASE
                                WHEN entry_key IN ('source', 'provider', 'search_provider')
                                     AND entry_value = to_jsonb(old_value)
                                THEN to_jsonb(new_value)
                                ELSE pg_temp.rewrite_ddgs_provenance(
                                    entry_value,
                                    old_value,
                                    new_value
                                )
                            END
                        );
                    END LOOP;
                    RETURN rewritten;
                END IF;

                IF jsonb_typeof(document) = 'array' THEN
                    SELECT COALESCE(
                        jsonb_agg(
                            pg_temp.rewrite_ddgs_provenance(
                                value,
                                old_value,
                                new_value
                            )
                            ORDER BY ordinality
                        ),
                        '[]'::jsonb
                    )
                    INTO rewritten
                    FROM jsonb_array_elements(document) WITH ORDINALITY;
                    RETURN rewritten;
                END IF;

                RETURN document;
            END;
            $$
            """
        )
    )
    for table_name, column_name in (
        ("web_evidence", "payload"),
        ("runs", "output_payload"),
        ("artifact_versions", "content"),
        ("domain_events", "payload"),
    ):
        op.execute(
            sa.text(
                f"""
                UPDATE {PRODUCT_SCHEMA}.{table_name}
                SET {column_name} = pg_temp.rewrite_ddgs_provenance(
                    {column_name},
                    '{old_value}',
                    '{new_value}'
                )
                WHERE {column_name}::text LIKE '%"{old_value}"%'
                """
            )
        )


def upgrade() -> None:
    _rewrite_provenance(LEGACY_PROVIDER, DDGS_PROVIDER)


def downgrade() -> None:
    _rewrite_provenance(DDGS_PROVIDER, LEGACY_PROVIDER)
