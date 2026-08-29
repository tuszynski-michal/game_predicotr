"""Allow unknown sentinel cells in topology-aware persisted layouts.

Revision ID: 0074_unknown_layout_cells
Revises: 0073_topology_geometry_crop_provenance
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0074_unknown_layout_cells"
down_revision: str | Sequence[str] | None = "0073_topology_geometry_crop_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_constraint(table: str, name: str, expression: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    _replace_constraint(
        "image_layout_staging_rows",
        "ck_image_layout_staging_cells",
        "cardinality(cells) > 0 AND 0 <= ALL(cells) AND 32767 >= ALL(cells)",
    )
    _replace_constraint(
        "layout_import_rows",
        "ck_layout_import_rows_cells_mobile_code_range",
        "cells IS NULL OR (0 <= ALL(cells) AND 32767 >= ALL(cells))",
    )
    _replace_constraint(
        "layout_import_normalized_rows",
        "ck_layout_import_normalized_rows_cells_code_range",
        "cells IS NULL OR (0 <= ALL(cells) AND 32767 >= ALL(cells))",
    )
    _replace_constraint(
        "layouts",
        "ck_layouts_cells_mobile_code_range",
        "0 <= ALL(cells) AND 32767 >= ALL(cells)",
    )


def downgrade() -> None:
    _replace_constraint(
        "layouts",
        "ck_layouts_cells_mobile_code_range",
        "1 <= ALL(cells) AND 32767 >= ALL(cells)",
    )
    _replace_constraint(
        "layout_import_normalized_rows",
        "ck_layout_import_normalized_rows_cells_code_range",
        "cells IS NULL OR (1 <= ALL(cells) AND 32767 >= ALL(cells))",
    )
    _replace_constraint(
        "layout_import_rows",
        "ck_layout_import_rows_cells_mobile_code_range",
        "cells IS NULL OR (1 <= ALL(cells) AND 32767 >= ALL(cells))",
    )
    _replace_constraint(
        "image_layout_staging_rows",
        "ck_image_layout_staging_cells",
        "cardinality(cells) = 15 AND 1 <= ALL(cells) AND 32767 >= ALL(cells)",
    )
