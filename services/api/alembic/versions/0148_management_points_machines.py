"""Add management control-plane metadata without changing existing records."""

from alembic import op

revision = "0148_management_points_machines"
down_revision = "0147_merge_v7_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE public.management_points (
	id UUID NOT NULL,
	name VARCHAR(200) NOT NULL,
	city VARCHAR(200) NOT NULL,
	street VARCHAR(200) NOT NULL,
	archived BOOLEAN NOT NULL,
	revision INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (revision >= 1)
)
    """)
    op.execute("""
CREATE TABLE public.management_machines (
	id UUID NOT NULL,
	point_id UUID NOT NULL,
	name VARCHAR(200) NOT NULL,
	archived BOOLEAN NOT NULL,
	revision INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (revision >= 1),
	FOREIGN KEY(point_id) REFERENCES public.management_points (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
CREATE INDEX ix_public_management_machines_point_id ON public.management_machines (point_id)
    """)
    op.execute("""
CREATE TABLE public.management_assignments (
	machine_id UUID NOT NULL,
	game_id UUID NOT NULL,
	attached BOOLEAN NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (machine_id, game_id),
	FOREIGN KEY(machine_id) REFERENCES public.management_machines (id) ON DELETE RESTRICT,
	FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
CREATE TABLE public.management_operations (
	operation_id UUID NOT NULL,
	actor VARCHAR(200) NOT NULL,
	request_checksum VARCHAR(64) NOT NULL,
	response JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (operation_id)
)
    """)
    op.execute("""
CREATE TABLE public.management_journal (
	id UUID NOT NULL,
	operation_id UUID NOT NULL,
	actor VARCHAR(200) NOT NULL,
	action VARCHAR(80) NOT NULL,
	point_id UUID NOT NULL,
	machine_id UUID,
	before JSON NOT NULL,
	after JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(operation_id) REFERENCES public.management_operations (operation_id)
        ON DELETE RESTRICT,
	FOREIGN KEY(point_id) REFERENCES public.management_points (id) ON DELETE RESTRICT,
	FOREIGN KEY(machine_id) REFERENCES public.management_machines (id) ON DELETE RESTRICT
)
    """)
    op.execute("""
CREATE INDEX ix_public_management_journal_created_at ON public.management_journal (created_at)
    """)
    op.execute("""
CREATE INDEX ix_public_management_journal_machine_id ON public.management_journal (machine_id)
    """)
    op.execute("""
CREATE INDEX ix_public_management_journal_operation_id ON public.management_journal (operation_id)
    """)
    op.execute("""
CREATE INDEX ix_public_management_journal_point_id ON public.management_journal (point_id)
    """)
    op.execute("""
        CREATE FUNCTION public.management_history_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Management history is immutable';
        END $$
    """)
    for table in ("management_operations", "management_journal"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.management_history_immutable()"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Management history cannot be deleted by downgrade. Restore a backup instead."
    )
