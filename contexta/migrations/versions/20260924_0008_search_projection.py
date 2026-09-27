from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_record", sa.Column("search_text", sa.Text(), nullable=True))
    op.execute(
        """
        CREATE OR REPLACE FUNCTION memory_record_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.search_text, NEW.content, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(array_to_string(NEW.tags, ' '), '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS memory_record_search_vector_trigger ON memory_record")
    op.execute(
        """
        CREATE TRIGGER memory_record_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, content, tags, search_text
        ON memory_record
        FOR EACH ROW
        EXECUTE FUNCTION memory_record_search_vector_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS memory_record_search_vector_trigger ON memory_record")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION memory_record_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(array_to_string(NEW.tags, ' '), '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_record_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, content, tags
        ON memory_record
        FOR EACH ROW
        EXECUTE FUNCTION memory_record_search_vector_update();
        """
    )
    op.drop_column("memory_record", "search_text")
