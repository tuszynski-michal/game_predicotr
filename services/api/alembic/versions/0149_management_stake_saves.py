"""Add durable independent stake slots and immutable compact history."""

from alembic import op

revision = "0149_management_stake_saves"
down_revision = "0148_management_points_machines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE public.management_result_versions (
        id UUID NOT NULL,
        game_id UUID NOT NULL,
        content_sha256 VARCHAR(64) NOT NULL,
        payload JSON NOT NULL,
        summary JSON NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (game_id, content_sha256),
        FOREIGN KEY(game_id) REFERENCES games (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
CREATE TABLE public.management_search_contexts (
        id UUID NOT NULL,
        machine_id UUID NOT NULL,
        game_id UUID NOT NULL,
        stake_grosze INTEGER NOT NULL,
        actor VARCHAR(200) NOT NULL,
        query JSON NOT NULL,
        sequence_numbers JSON NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(machine_id, game_id) REFERENCES public.management_assignments
(machine_id, game_id) ON DELETE RESTRICT,
        CHECK (stake_grosze IN (2000,1000,600,400,200,120)),
        FOREIGN KEY(id) REFERENCES public.management_operations (operation_id) ON DELETE
RESTRICT
)
    """)
    op.execute("""
CREATE TABLE public.management_stake_slots (
        machine_id UUID NOT NULL,
        game_id UUID NOT NULL,
        stake_grosze INTEGER NOT NULL,
        revision INTEGER NOT NULL,
        search_context_id UUID,
        start_sequence_number INTEGER,
        spin_count INTEGER,
        pinned_spin_positions JSON NOT NULL,
        pinned_points JSON NOT NULL,
        result_version_id UUID,
        stale_error_code VARCHAR(100),
        saved_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (machine_id, game_id, stake_grosze),
        FOREIGN KEY(machine_id, game_id) REFERENCES public.management_assignments
(machine_id, game_id) ON DELETE RESTRICT,
        CHECK (stake_grosze IN (2000,1000,600,400,200,120)),
        CHECK (revision >= 1),
        CHECK (spin_count IS NULL OR spin_count BETWEEN 1 AND 100000),
        CHECK (start_sequence_number IS NULL OR start_sequence_number >= 1),
        CHECK ((result_version_id IS NULL AND search_context_id IS NULL AND
start_sequence_number IS NULL AND spin_count IS NULL) OR (result_version_id IS NOT NULL
AND search_context_id IS NOT NULL AND start_sequence_number IS NOT NULL AND spin_count IS
NOT NULL)),
        FOREIGN KEY(search_context_id) REFERENCES public.management_search_contexts (id)
ON DELETE RESTRICT,
        FOREIGN KEY(result_version_id) REFERENCES public.management_result_versions (id)
ON DELETE RESTRICT
)
    """)
    op.execute("""
CREATE INDEX ix_public_management_stake_slots_result_version_id ON
public.management_stake_slots (result_version_id)
    """)
    op.execute("""
ALTER TABLE public.management_journal ADD COLUMN game_id UUID REFERENCES public.games(id)
ON DELETE RESTRICT
    """)
    op.execute("""
ALTER TABLE public.management_journal ADD COLUMN stake_grosze INTEGER
    """)
    op.execute("""
ALTER TABLE public.management_journal ADD COLUMN before_result_id UUID REFERENCES
public.management_result_versions(id) ON DELETE RESTRICT
    """)
    op.execute("""
ALTER TABLE public.management_journal ADD COLUMN after_result_id UUID REFERENCES
public.management_result_versions(id) ON DELETE RESTRICT
    """)
    op.execute("""
CREATE INDEX ix_management_journal_slot_page ON public.management_journal(machine_id,
game_id, stake_grosze, created_at DESC, id DESC)
    """)
    op.execute("""
CREATE INDEX ix_management_journal_result_before ON
public.management_journal(machine_id,game_id,before_result_id)
    """)
    op.execute("""
CREATE INDEX ix_management_journal_result_after ON
public.management_journal(machine_id,game_id,after_result_id)
    """)
    op.execute("""
CREATE TRIGGER management_result_versions_immutable BEFORE UPDATE OR DELETE ON
public.management_result_versions FOR EACH ROW EXECUTE FUNCTION
public.management_history_immutable()
    """)
    op.execute("""
CREATE TRIGGER management_search_contexts_immutable BEFORE UPDATE OR DELETE ON
public.management_search_contexts FOR EACH ROW EXECUTE FUNCTION
public.management_history_immutable()
    """)


def downgrade() -> None:
    raise RuntimeError("Management saved history is retained; restore a backup instead.")
