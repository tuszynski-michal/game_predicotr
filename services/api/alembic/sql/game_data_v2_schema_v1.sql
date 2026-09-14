-- Frozen TASK-0518 DDL, manifest game-data-v2-manifest-v1.
-- No runtime ORM imports, data copy, game partitions or legacy triggers.

CREATE TABLE game_data_v2.browser_selection_retention_states (
	upload_id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID,
	display_name VARCHAR(255) NOT NULL,
	state VARCHAR(24) NOT NULL,
	manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	managed_manifest_relative_path TEXT,
	managed_manifest_checksum_sha256 VARCHAR(64),
	finalized_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_dependency_at TIMESTAMP WITH TIME ZONE,
	eligible_at TIMESTAMP WITH TIME ZONE,
	blocked_reason VARCHAR(100),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_f232e5ed604dc2f26726 PRIMARY KEY (game_id, upload_id),
	CONSTRAINT ck_browser_selection_retention_state CHECK (state IN ('ready', 'in_use', 'ingested', 'cleanup_eligible', 'blocked')),
	CONSTRAINT ck_browser_selection_retention_checksums CHECK (manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND (managed_manifest_checksum_sha256 IS NULL OR managed_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_browser_selection_retention_managed_manifest CHECK ((managed_manifest_relative_path IS NULL) = (managed_manifest_checksum_sha256 IS NULL))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.cell_observations (
	id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	row_index SMALLINT NOT NULL,
	column_index SMALLINT NOT NULL,
	asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	source_geometry_revision_id UUID,
	logical_cell_key VARCHAR(64),
	logical_cell_key_v2 VARCHAR(64),
	render_identity_v2_sha256 VARCHAR(64),
	render_spec JSONB,
	render_spec_checksum_sha256 VARCHAR(64),
	rendered_pixel_checksum_sha256 VARCHAR(64),
	extractor_version VARCHAR(150),
	crop_relative_path VARCHAR(1000),
	crop_checksum_sha256 VARCHAR(64) NOT NULL,
	cropper_version VARCHAR(150) NOT NULL,
	prediction JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_f08239a9ad51dd216330 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_cell_observations_checksum CHECK (crop_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_cell_observations_asset_provenance CHECK ((asset_mode = 'legacy_file' AND length(btrim(crop_relative_path)) > 0 AND crop_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)') OR (asset_mode = 'virtual_source' AND crop_relative_path IS NULL AND source_geometry_revision_id IS NOT NULL AND logical_cell_key ~ '^[0-9a-f]{64}$' AND jsonb_typeof(render_spec) = 'object' AND render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(extractor_version)) > 0)),
	CONSTRAINT ck_cell_observations_v2_identity CHECK ((logical_cell_key_v2 IS NULL AND render_identity_v2_sha256 IS NULL) OR (logical_cell_key_v2 ~ '^[0-9a-f]{64}$' AND render_identity_v2_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_cell_observations_coordinates CHECK (row_index BETWEEN 0 AND 2 AND column_index BETWEEN 0 AND 4),
	CONSTRAINT v2_uq_c9297ec2af37f60028a0 UNIQUE (game_id, recognized_board_id, row_index, column_index)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.curated_image_import_batches (
	id UUID NOT NULL,
	source_id UUID NOT NULL,
	batch_number INTEGER NOT NULL,
	start_index BIGINT NOT NULL,
	end_index BIGINT NOT NULL,
	job_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_354406efbd8ff5918050 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_curated_image_import_batches_range CHECK (batch_number > 0 AND start_index >= 0 AND end_index > start_index),
	CONSTRAINT v2_uq_42e22cfb72c926fe290b UNIQUE (game_id, source_id, batch_number),
	CONSTRAINT v2_uq_b76ef0861848d70f9d24 UNIQUE (game_id, job_id),
	CONSTRAINT v2_uq_24fdce9dfaab0ecc037f UNIQUE (game_id, source_id, start_index)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.curated_image_import_sources (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	image_selection_run_id UUID NOT NULL,
	manifest_relative_path VARCHAR(1000) NOT NULL,
	manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	total_entries BIGINT NOT NULL,
	next_entry_index BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_ead7465d75d9e1ba8339 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_curated_image_import_sources_cursor CHECK (total_entries > 0 AND next_entry_index >= 0 AND next_entry_index <= total_entries),
	CONSTRAINT ck_curated_image_import_sources_manifest_checksum CHECK (manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_curated_image_import_sources_manifest_path CHECK (manifest_relative_path !~ '(^|/)\.\.(/|$)' AND manifest_relative_path !~ '^[A-Za-z]:' AND manifest_relative_path NOT LIKE '/%' AND manifest_relative_path NOT LIKE '%\\%'),
	CONSTRAINT v2_uq_2d2426a319a7a809aae7 UNIQUE (game_id, image_selection_run_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.dataset_versions (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	version INTEGER NOT NULL,
	rows SMALLINT NOT NULL,
	columns SMALLINT NOT NULL,
	signature_cell_width SMALLINT NOT NULL,
	expected_layout_count BIGINT NOT NULL,
	layout_count BIGINT NOT NULL,
	status dataset_version_status NOT NULL,
	generation_seed BIGINT NOT NULL,
	generator_version VARCHAR(64) NOT NULL,
	source_job_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT v2_pk_c8f6aca356073b684b92 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_dataset_versions_expected_layout_count_range CHECK (expected_layout_count BETWEEN 1 AND 10000000),
	CONSTRAINT ck_dataset_versions_version_positive CHECK (version > 0),
	CONSTRAINT ck_dataset_versions_rows_range CHECK (rows BETWEEN 1 AND 32767),
	CONSTRAINT ck_dataset_versions_layout_count_nonnegative CHECK (layout_count >= 0),
	CONSTRAINT ck_dataset_versions_columns_range CHECK (columns BETWEEN 1 AND 32767),
	CONSTRAINT ck_dataset_versions_signature_width_range CHECK (signature_cell_width BETWEEN 1 AND 5),
	CONSTRAINT ck_dataset_versions_generation_seed_range CHECK (generation_seed BETWEEN 0 AND 2147483647),
	CONSTRAINT v2_uq_a21472b2243dc37cd263 UNIQUE (game_id, version)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.game_grid_profile_activations (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	profile_id UUID NOT NULL,
	previous_profile_id UUID,
	action VARCHAR(20) NOT NULL,
	activation_number INTEGER NOT NULL,
	actor VARCHAR(200) NOT NULL,
	reason TEXT,
	idempotency_key UUID NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_5cbbb87755902ae23277 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_game_grid_profile_activations_values CHECK (activation_number > 0 AND btrim(actor) <> '' AND command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_game_grid_profile_activations_action CHECK (action IN ('activate','rollback')),
	CONSTRAINT v2_uq_4e73de0fdf5f5760d758 UNIQUE (game_id, activation_number),
	CONSTRAINT v2_uq_c20d05a2b6c676570fb0 UNIQUE (game_id, idempotency_key)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.game_symbol_model_activations (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	model_iteration_id UUID NOT NULL,
	previous_model_iteration_id UUID,
	action VARCHAR(20) NOT NULL,
	activation_number INTEGER NOT NULL,
	actor VARCHAR(200) NOT NULL,
	reason TEXT,
	idempotency_key UUID NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_22a192157f8a2f05725b PRIMARY KEY (game_id, id),
	CONSTRAINT ck_game_symbol_model_activations_values CHECK (activation_number > 0 AND btrim(actor) <> '' AND command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_game_symbol_model_activations_action CHECK (action IN ('activate','rollback')),
	CONSTRAINT v2_uq_0eaca4e6a7cea6b4cc24 UNIQUE (game_id, idempotency_key),
	CONSTRAINT v2_uq_3efcf0d17fdc8e7d07e5 UNIQUE (game_id, activation_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.grid_calibration_profiles (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	cohort_id UUID NOT NULL,
	profile_number INTEGER NOT NULL,
	status VARCHAR(30) NOT NULL,
	profile_checksum_sha256 VARCHAR(64) NOT NULL,
	profile_payload JSONB NOT NULL,
	gate_metrics JSONB NOT NULL,
	rejection_reasons VARCHAR(100)[] NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_63fdfd0fdc9c80bb63d1 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_grid_calibration_profiles_checksum CHECK (profile_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_grid_calibration_profiles_values CHECK (profile_number > 0 AND status IN ('candidate_ready','rejected')),
	CONSTRAINT v2_uq_513b6c5c87cfe0b139e4 UNIQUE (game_id, profile_number),
	CONSTRAINT v2_uq_ed56c628768ba958038b UNIQUE (game_id, cohort_id, profile_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.grid_geometry_cohorts (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	cohort_number INTEGER NOT NULL,
	manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	manifest_payload JSONB NOT NULL,
	sample_count INTEGER NOT NULL,
	source_image_count INTEGER NOT NULL,
	training_count INTEGER NOT NULL,
	validation_count INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_fde1805b9524b1e3cec6 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_grid_geometry_cohorts_counts CHECK (cohort_number > 0 AND sample_count > 0 AND source_image_count > 0 AND training_count >= 0 AND validation_count >= 0 AND training_count + validation_count = sample_count),
	CONSTRAINT ck_grid_geometry_cohorts_manifest_checksum CHECK (manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_88c2c126568eebf997dc UNIQUE (game_id, cohort_number),
	CONSTRAINT v2_uq_bd110b761afd15f6c3ca UNIQUE (game_id, manifest_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_board_geometry_pending (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	source_image_id UUID NOT NULL,
	recognized_board_id UUID,
	review_item_id UUID,
	sequence_number BIGINT NOT NULL,
	position_index SMALLINT NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	source_relative_path VARCHAR(1000) NOT NULL,
	status VARCHAR(20) NOT NULL,
	reason_code VARCHAR(40) NOT NULL,
	processing_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	processing_manifest_relative_path VARCHAR(1000) NOT NULL,
	pipeline_fingerprint_sha256 VARCHAR(64) NOT NULL,
	expected_geometry_revision INTEGER NOT NULL,
	expected_review_resolution_revision INTEGER NOT NULL,
	resolved_geometry_revision INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	resolved_at TIMESTAMP WITH TIME ZONE,
	superseded_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT v2_pk_bde39d91b28a81bbeb70 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_board_geometry_pending_reason CHECK (reason_code IN ('insufficient_centers', 'incomplete_lattice', 'residual_too_high', 'source_unavailable')),
	CONSTRAINT ck_image_board_geometry_pending_lifecycle CHECK ((status = 'pending' AND resolved_geometry_revision IS NULL AND resolved_at IS NULL AND superseded_at IS NULL) OR (status = 'resolved' AND resolved_geometry_revision IS NOT NULL AND resolved_geometry_revision > expected_geometry_revision AND resolved_at IS NOT NULL AND superseded_at IS NULL) OR (status = 'superseded' AND resolved_geometry_revision IS NULL AND resolved_at IS NULL AND superseded_at IS NOT NULL)),
	CONSTRAINT ck_image_board_geometry_pending_status CHECK (status IN ('pending', 'resolved', 'superseded')),
	CONSTRAINT ck_image_board_geometry_pending_checksums CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND processing_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND pipeline_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_board_geometry_pending_paths CHECK (length(btrim(source_relative_path)) > 0 AND source_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)' AND length(btrim(processing_manifest_relative_path)) > 0 AND processing_manifest_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_image_board_geometry_pending_values CHECK (sequence_number > 0 AND position_index BETWEEN 0 AND 8 AND expected_geometry_revision >= 0 AND expected_review_resolution_revision >= 0),
	CONSTRAINT v2_uq_09714efe765ed193f209 UNIQUE (game_id, import_job_id, source_image_id, position_index, processing_manifest_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_board_geometry_review_events (
	id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	geometry_revision INTEGER NOT NULL,
	grid_rows SMALLINT NOT NULL,
	grid_columns SMALLINT NOT NULL,
	board_checksum_sha256 VARCHAR(64) NOT NULL,
	action VARCHAR(30) NOT NULL,
	previous_approved_geometry_revision INTEGER,
	approved_geometry_revision INTEGER NOT NULL,
	actor VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_925e1cf0ce7b149f7d47 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_board_geometry_review_events_revisions CHECK (geometry_revision >= 0 AND approved_geometry_revision >= 0 AND approved_geometry_revision <= geometry_revision),
	CONSTRAINT ck_image_board_geometry_review_events_topology CHECK (grid_rows > 0 AND grid_columns > 0),
	CONSTRAINT ck_image_board_geometry_review_events_checksum CHECK (board_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_board_geometry_review_events_action CHECK (action IN ('approved', 'geometry_saved', 'backfilled'))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_board_geometry_revisions (
	id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	idempotency_key UUID NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	corners JSONB NOT NULL,
	geometry JSONB NOT NULL,
	asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	source_geometry_revision_id UUID,
	geometry_checksum_sha256 VARCHAR(64),
	virtual_render_spec JSONB,
	virtual_render_spec_checksum_sha256 VARCHAR(64),
	board_relative_path VARCHAR(1000),
	board_checksum_sha256 VARCHAR(64),
	cropper_version VARCHAR(150) NOT NULL,
	crop_artifacts JSONB,
	corrected_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_08f7541752ca6b7a8834 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_board_geometry_revisions_asset CHECK ((asset_mode = 'legacy_file' AND board_checksum_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(board_relative_path)) > 0 AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)' AND jsonb_typeof(crop_artifacts) = 'array' AND jsonb_array_length(crop_artifacts) = 15) OR (asset_mode = 'virtual_source' AND board_relative_path IS NULL AND board_checksum_sha256 IS NULL AND crop_artifacts IS NULL AND source_geometry_revision_id IS NOT NULL AND geometry_checksum_sha256 ~ '^[0-9a-f]{64}$' AND jsonb_typeof(virtual_render_spec) = 'object' AND virtual_render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_image_board_geometry_revisions_revision CHECK (revision > 0),
	CONSTRAINT ck_image_board_geometry_revisions_corners CHECK (jsonb_typeof(corners) = 'array' AND jsonb_array_length(corners) = 4),
	CONSTRAINT ck_image_board_geometry_revisions_command_checksum CHECK (command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_4f35498156c6f65a659c UNIQUE (game_id, recognized_board_id, revision),
	CONSTRAINT v2_uq_00cccf891d00462312b0 UNIQUE (game_id, review_item_id, idempotency_key)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_board_search_candidates (
	review_item_id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	status VARCHAR(20) NOT NULL,
	board_checksum_sha256 VARCHAR(64) NOT NULL,
	board_confidence FLOAT NOT NULL,
	sequence_confidence FLOAT NOT NULL,
	source_pixel_count BIGINT NOT NULL,
	primary_symbol_codes JSONB NOT NULL,
	alternative_symbol_codes JSONB NOT NULL,
	known_evidence_positions VARCHAR(2)[] NOT NULL,
	primary_symbol_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_1_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_2_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_3_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_4_mobile_codes SMALLINT[] NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_f0ce60b05e2fd3d26953 PRIMARY KEY (game_id, review_item_id),
	CONSTRAINT ck_image_board_search_candidates_alternative_cells CHECK (jsonb_typeof(alternative_symbol_codes) = 'array' AND jsonb_array_length(alternative_symbol_codes) = 15),
	CONSTRAINT ck_image_board_search_candidates_sequence_positive CHECK (sequence_number > 0),
	CONSTRAINT ck_image_board_search_candidates_status CHECK (status IN ('pending', 'accepted', 'corrected')),
	CONSTRAINT ck_image_board_search_candidates_scores CHECK (board_confidence BETWEEN 0 AND 1 AND sequence_confidence BETWEEN 0 AND 1 AND source_pixel_count > 0),
	CONSTRAINT ck_image_board_search_candidates_primary_cells CHECK (jsonb_typeof(primary_symbol_codes) = 'array' AND jsonb_array_length(primary_symbol_codes) = 15),
	CONSTRAINT ck_image_board_search_candidates_checksum CHECK (board_checksum_sha256 ~ '^[0-9a-f]{64}$')
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_board_search_fast_documents (
	game_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	status VARCHAR(20) NOT NULL,
	board_checksum_sha256 VARCHAR(64) NOT NULL,
	known_evidence_positions VARCHAR(2)[] NOT NULL,
	primary_symbol_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_1_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_2_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_3_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_4_mobile_codes SMALLINT[] NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_077768815a36ef1872f4 PRIMARY KEY (game_id, sequence_number),
	CONSTRAINT ck_image_board_search_fast_documents_status CHECK (status IN ('pending', 'accepted', 'corrected')),
	CONSTRAINT ck_image_board_search_fast_documents_sequence_positive CHECK (sequence_number > 0),
	CONSTRAINT v2_uq_09d99d9f95d16d384041 UNIQUE (game_id, review_item_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_board_search_projection_states (
	game_id UUID NOT NULL,
	status VARCHAR(20) NOT NULL,
	candidate_count BIGINT NOT NULL,
	document_count BIGINT NOT NULL,
	skipped_review_item_count BIGINT NOT NULL,
	failure_message VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_82f47d6b5a22e48e3e05 PRIMARY KEY (game_id),
	CONSTRAINT ck_image_board_search_projection_states_status CHECK (status IN ('rebuilding', 'ready', 'failed')),
	CONSTRAINT ck_image_board_search_projection_states_counts CHECK (candidate_count >= 0 AND document_count >= 0 AND skipped_review_item_count >= 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_geometry_rollout_states (
	game_id UUID NOT NULL,
	geometry_mode VARCHAR(30) DEFAULT 'legacy' NOT NULL,
	cell_asset_mode VARCHAR(30) DEFAULT 'legacy_files' NOT NULL,
	revision INTEGER DEFAULT 0 NOT NULL,
	backfill_status VARCHAR(20) DEFAULT 'not_started' NOT NULL,
	last_source_image_id UUID,
	failure_code VARCHAR(100),
	failure_message TEXT,
	validation_rollout_revision INTEGER,
	validation_input_checksum_sha256 VARCHAR(64),
	validation_job_id UUID,
	updated_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_e9594ea2d28c1167eb9d PRIMARY KEY (game_id),
	CONSTRAINT ck_image_geometry_rollout_states_validation_binding CHECK ((validation_rollout_revision IS NULL AND validation_input_checksum_sha256 IS NULL AND validation_job_id IS NULL) OR (validation_rollout_revision >= 0 AND validation_input_checksum_sha256 ~ '^[0-9a-f]{64}$' AND validation_job_id IS NOT NULL)),
	CONSTRAINT ck_image_geometry_rollout_states_geometry_mode CHECK (geometry_mode IN ('legacy', 'structured_shadow', 'structured_review', 'structured_default', 'structured_lattice_v3')),
	CONSTRAINT ck_image_geometry_rollout_states_progress CHECK (revision >= 0 AND backfill_status IN ('not_started', 'processing', 'ready', 'failed')),
	CONSTRAINT ck_image_geometry_rollout_states_failure CHECK (length(btrim(updated_by)) > 0 AND ((backfill_status = 'failed' AND failure_code IS NOT NULL AND failure_message IS NOT NULL) OR (backfill_status <> 'failed' AND failure_code IS NULL AND failure_message IS NULL))),
	CONSTRAINT ck_image_geometry_rollout_states_asset_mode CHECK (cell_asset_mode IN ('legacy_files', 'virtual_shadow', 'virtual_default'))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_import_geometry_guard_decisions (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	browser_selection_id UUID NOT NULL,
	guard_job_id UUID NOT NULL,
	guard_report_checksum_sha256 VARCHAR(64) NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	source_relative_path VARCHAR(1000) NOT NULL,
	position_index SMALLINT NOT NULL,
	sequence_number BIGINT NOT NULL,
	revision INTEGER NOT NULL,
	disposition VARCHAR(24) NOT NULL,
	geometry_qualification JSONB,
	symbol_grid_quad JSONB,
	unavailable_cell_indices SMALLINT[] DEFAULT '{}' NOT NULL,
	reason VARCHAR(200),
	actor VARCHAR(200) NOT NULL,
	decision_checksum_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_b386729fcad2dc1777a3 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_import_guard_decisions_values CHECK (position_index BETWEEN 0 AND 8 AND sequence_number > 0 AND revision > 0),
	CONSTRAINT ck_image_import_guard_decisions_text CHECK (length(btrim(source_relative_path)) > 0 AND source_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)' AND length(btrim(actor)) > 0),
	CONSTRAINT ck_guard_decisions_qualification CHECK (geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = 'object' AND ((geometry_qualification->>'version' = 'manual-geometry-qualification-v1' AND NOT (geometry_qualification ? 'includeInPartialGridTraining')) OR (geometry_qualification->>'version' = 'manual-geometry-qualification-v2' AND jsonb_typeof(geometry_qualification->'includeInPartialGridTraining') = 'boolean')) AND geometry_qualification->'unavailableCellIndices' = to_jsonb(unavailable_cell_indices) AND ((disposition = 'partial' AND geometry_qualification->>'completenessStatus' = 'pending_partial' AND geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'missing_pixels') OR (disposition = 'corrected_full' AND geometry_qualification->>'completenessStatus' = 'complete' AND COALESCE(geometry_qualification->'includeInPartialGridTraining', 'false'::jsonb) = 'false'::jsonb AND ((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR (geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)),
	CONSTRAINT ck_image_import_guard_decisions_disposition CHECK ((disposition = 'corrected_full' AND symbol_grid_quad IS NOT NULL AND jsonb_typeof(symbol_grid_quad) = 'array' AND jsonb_array_length(symbol_grid_quad) = 4 AND cardinality(unavailable_cell_indices) = 0) OR (disposition = 'partial' AND symbol_grid_quad IS NOT NULL AND jsonb_typeof(symbol_grid_quad) = 'array' AND jsonb_array_length(symbol_grid_quad) = 4 AND cardinality(unavailable_cell_indices) BETWEEN 1 AND 15 AND unavailable_cell_indices <@ ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]::smallint[]) OR (disposition = 'rejected' AND symbol_grid_quad IS NULL AND cardinality(unavailable_cell_indices) = 0 AND length(btrim(reason)) > 0)),
	CONSTRAINT ck_image_import_guard_decisions_checksums CHECK (guard_report_checksum_sha256 ~ '^[0-9a-f]{64}$' AND source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND decision_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_af7495203dfc6c7967b6 UNIQUE (game_id, guard_job_id, source_checksum_sha256, position_index, revision),
	CONSTRAINT v2_uq_07f8e2096dade4ef4c1e UNIQUE (game_id, guard_job_id, decision_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_import_geometry_guard_resolution_manifests (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	browser_selection_id UUID NOT NULL,
	guard_job_id UUID NOT NULL,
	guard_report_checksum_sha256 VARCHAR(64) NOT NULL,
	source_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	page_geometry_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	manifest_relative_path VARCHAR(1000) NOT NULL,
	manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	decision_count INTEGER NOT NULL,
	sealed_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_0af2bffafb4154ef9118 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_import_guard_resolution_manifest_values CHECK (decision_count > 0 AND length(btrim(sealed_by)) > 0 AND length(btrim(manifest_relative_path)) > 0 AND manifest_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_image_import_guard_resolution_manifest_checksums CHECK (guard_report_checksum_sha256 ~ '^[0-9a-f]{64}$' AND source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND page_geometry_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_0103d71ad235ff81eff7 UNIQUE (game_id, guard_job_id, manifest_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_import_job_files (
	job_id UUID NOT NULL,
	file_execution_key VARCHAR(64) NOT NULL,
	order_index BIGINT NOT NULL,
	source_relative_path VARCHAR(1000) NOT NULL,
	workflow_checkpoint_payload JSONB NOT NULL,
	workflow_status VARCHAR(30) NOT NULL,
	review_required BOOLEAN DEFAULT false NOT NULL,
	failed_stage VARCHAR(40),
	error_code VARCHAR(100),
	error_message TEXT,
	retry_count INTEGER DEFAULT 0 NOT NULL,
	last_failed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_a920f6b4053203b36ffe PRIMARY KEY (game_id, job_id, file_execution_key),
	CONSTRAINT ck_image_import_job_files_failure_state CHECK ((workflow_status = 'failed' AND failed_stage IS NOT NULL AND error_code IS NOT NULL AND error_message IS NOT NULL AND last_failed_at IS NOT NULL) OR (workflow_status <> 'failed' AND failed_stage IS NULL AND error_code IS NULL AND error_message IS NULL AND last_failed_at IS NULL)),
	CONSTRAINT ck_image_import_job_files_workflow_status CHECK (workflow_status IN ('processing', 'waiting_for_review', 'completed', 'failed')),
	CONSTRAINT ck_image_import_job_files_retry_nonnegative CHECK (retry_count >= 0),
	CONSTRAINT ck_image_import_job_files_order_nonnegative CHECK (order_index >= 0),
	CONSTRAINT ck_image_import_job_files_relative_path CHECK (source_relative_path <> '' AND source_relative_path !~ '(^|/)\.\.(/|$)' AND source_relative_path !~ '^/' AND source_relative_path !~ '\\'),
	CONSTRAINT v2_uq_f9b8a3623cd5496118eb UNIQUE (game_id, job_id, order_index)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_layout_staging_rows (
	import_job_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	cells SMALLINT[] NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_4e285c384562d25380d9 PRIMARY KEY (game_id, import_job_id, recognized_board_id),
	CONSTRAINT ck_image_layout_staging_sequence_positive CHECK (sequence_number > 0),
	CONSTRAINT ck_image_layout_staging_cells CHECK (cardinality(cells) > 0 AND 0 <= ALL(cells) AND 32767 >= ALL(cells)),
	CONSTRAINT v2_uq_694a139b699bb13f7afe UNIQUE (game_id, review_item_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_page_geometry_overrides (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	image_width INTEGER NOT NULL,
	image_height INTEGER NOT NULL,
	final_quads JSONB NOT NULL,
	slot_qualifications JSONB,
	revision INTEGER NOT NULL,
	actor VARCHAR(200) NOT NULL,
	decision_checksum_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_832849bcea935f7c693f PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_page_geometry_overrides_checksums CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND decision_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_page_geometry_overrides_values CHECK (image_width > 0 AND image_height > 0 AND revision > 0),
	CONSTRAINT ck_page_override_slot_qualifications CHECK (slot_qualifications IS NULL OR (CASE WHEN jsonb_typeof(slot_qualifications) = 'array' THEN jsonb_array_length(slot_qualifications) = jsonb_array_length(final_quads) ELSE false END)),
	CONSTRAINT ck_image_page_geometry_overrides_quads CHECK (jsonb_typeof(final_quads) = 'array' AND jsonb_array_length(final_quads) BETWEEN 1 AND 9),
	CONSTRAINT v2_uq_82bce614118ccd5d0454 UNIQUE (game_id, source_checksum_sha256, revision)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_page_source_exclusions (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	browser_selection_id UUID NOT NULL,
	geometry_preflight_job_id UUID NOT NULL,
	source_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	geometry_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	source_relative_path VARCHAR(1000) NOT NULL,
	actor VARCHAR(200) NOT NULL,
	decision_checksum_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_b149872924b3a84e70dc PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_page_source_exclusions_checksums CHECK (source_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND geometry_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND decision_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_page_source_exclusions_text CHECK (length(btrim(source_relative_path)) > 0 AND source_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)' AND length(btrim(actor)) > 0),
	CONSTRAINT v2_uq_48326fff24a4dfbaaedc UNIQUE (game_id, browser_selection_id, source_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_review_items (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	sequence_number BIGINT,
	recognized_board_id UUID NOT NULL,
	status VARCHAR(20) NOT NULL,
	snapshot JSONB NOT NULL,
	resolved_value JSONB,
	resolved_by VARCHAR(200),
	resolution_revision INTEGER DEFAULT 0 NOT NULL,
	resolved_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_b55f1be1aa532f9a74c1 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_review_items_resolution_state CHECK ((status = 'pending' AND resolved_value IS NULL AND resolved_by IS NULL AND resolved_at IS NULL AND resolution_revision >= 0) OR (status <> 'pending' AND resolved_value IS NOT NULL AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL AND resolution_revision > 0)),
	CONSTRAINT ck_image_review_items_status CHECK (status IN ('pending', 'accepted', 'corrected', 'rejected', 'superseded')),
	CONSTRAINT v2_uq_bd2a579dad98ec3dc142 UNIQUE (game_id, recognized_board_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_review_queue_items (
	review_item_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	source_order_index BIGINT NOT NULL,
	position_index SMALLINT NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_5190a34a41ee956518d5 PRIMARY KEY (game_id, review_item_id),
	CONSTRAINT ck_image_review_queue_items_status CHECK (status IN ('pending', 'accepted', 'corrected', 'rejected', 'superseded')),
	CONSTRAINT ck_image_review_queue_items_position CHECK (source_order_index >= 0 AND position_index BETWEEN 0 AND 8),
	CONSTRAINT v2_uq_4c37baab316b781d20d5 UNIQUE (game_id, import_job_id, source_order_index, position_index, review_item_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_review_queue_states (
	import_job_id UUID NOT NULL,
	queue_version BIGINT NOT NULL,
	total_count BIGINT NOT NULL,
	pending_count BIGINT NOT NULL,
	accepted_count BIGINT NOT NULL,
	corrected_count BIGINT NOT NULL,
	rejected_count BIGINT NOT NULL,
	superseded_count BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_d8c64ac9090188fe8ab0 PRIMARY KEY (game_id, import_job_id),
	CONSTRAINT ck_image_review_queue_states_total CHECK (total_count = pending_count + accepted_count + corrected_count + rejected_count + superseded_count),
	CONSTRAINT ck_image_review_queue_states_nonnegative CHECK (queue_version > 0 AND total_count >= 0 AND pending_count >= 0 AND accepted_count >= 0 AND corrected_count >= 0 AND rejected_count >= 0 AND superseded_count >= 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_review_resolution_events (
	id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	idempotency_key UUID NOT NULL,
	action VARCHAR(20) NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	resolved_value JSONB NOT NULL,
	resolved_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_e325ecabd2402988ad6d PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_review_resolution_events_revision CHECK (revision > 0),
	CONSTRAINT ck_image_review_resolution_events_command CHECK (command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_review_resolution_events_action CHECK (action IN ('accepted', 'corrected', 'rejected', 'reopened', 'superseded')),
	CONSTRAINT v2_uq_73514fa0c50f4a273c7b UNIQUE (game_id, review_item_id, idempotency_key),
	CONSTRAINT v2_uq_cebaa118ee129a80a634 UNIQUE (game_id, review_item_id, revision)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_selection_candidates (
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	group_id UUID,
	order_index BIGINT NOT NULL,
	source_relative_path VARCHAR(1000) NOT NULL,
	checksum_sha256 VARCHAR(64) NOT NULL,
	width INTEGER NOT NULL,
	height INTEGER NOT NULL,
	quality_metrics JSONB NOT NULL,
	range_confidence FLOAT,
	reason_codes JSONB NOT NULL,
	decision VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_d5388d517a0278a6ec0d PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_selection_candidates_quality_metrics CHECK (jsonb_typeof(quality_metrics) = 'object'),
	CONSTRAINT ck_image_selection_candidates_selected_group CHECK (decision NOT IN ('selected_automatic', 'selected_manual') OR group_id IS NOT NULL),
	CONSTRAINT ck_image_selection_candidates_order_nonnegative CHECK (order_index >= 0),
	CONSTRAINT ck_image_selection_candidates_range_confidence CHECK (range_confidence IS NULL OR range_confidence BETWEEN 0 AND 1),
	CONSTRAINT ck_image_selection_candidates_decision CHECK (decision IN ('eligible', 'rejected', 'selected_automatic', 'selected_manual')),
	CONSTRAINT ck_image_selection_candidates_dimensions CHECK (width >= 1 AND height >= 1),
	CONSTRAINT ck_image_selection_candidates_reason_codes CHECK (jsonb_typeof(reason_codes) = 'array'),
	CONSTRAINT ck_image_selection_candidates_source_path_safe CHECK (source_relative_path !~ '(^|/)\.\.(/|$)' AND source_relative_path !~ '^[A-Za-z]:' AND source_relative_path NOT LIKE '/%' AND source_relative_path NOT LIKE '%\\%'),
	CONSTRAINT ck_image_selection_candidates_checksum_sha256 CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_434e606d6dd0406b0280 UNIQUE (game_id, run_id, source_relative_path),
	CONSTRAINT v2_uq_5cb679384fcc72c6d04b UNIQUE (game_id, run_id, order_index)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_selection_groups (
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	group_order BIGINT NOT NULL,
	range_start BIGINT,
	range_end BIGINT,
	fingerprint_sha256 VARCHAR(64),
	board_count_consensus SMALLINT,
	status VARCHAR(40) NOT NULL,
	rejection_origin_status VARCHAR(40),
	origin_group_id UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_36e9adbddeabe8403a02 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_selection_groups_fingerprint_sha256 CHECK (fingerprint_sha256 IS NULL OR fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_selection_groups_range CHECK ((range_start IS NULL AND range_end IS NULL) OR (range_start >= 1 AND range_end >= range_start)),
	CONSTRAINT ck_image_selection_groups_rejection_origin CHECK ((status = 'rejected_by_user' AND rejection_origin_status IN ('manual_required', 'range_required')) OR (status <> 'rejected_by_user' AND rejection_origin_status IS NULL)),
	CONSTRAINT ck_image_selection_groups_board_count CHECK (board_count_consensus IS NULL OR board_count_consensus BETWEEN 1 AND 9),
	CONSTRAINT ck_image_selection_groups_status CHECK (status IN ('collecting', 'auto_selected', 'manual_required', 'manually_selected', 'missing_image', 'skipped_existing_range', 'range_required', 'range_confirmed', 'skipped_unreadable', 'rejected_by_user')),
	CONSTRAINT ck_image_selection_groups_order_nonnegative CHECK (group_order >= 0),
	CONSTRAINT v2_uq_7ee34753e2d5eb77d64a UNIQUE (game_id, run_id, group_order),
	CONSTRAINT v2_uq_2ccc487a642d40de3f8d UNIQUE (game_id, run_id, id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_selection_manual_decisions (
	idempotency_key UUID NOT NULL,
	run_id UUID NOT NULL,
	group_id UUID NOT NULL,
	candidate_id UUID,
	resolution VARCHAR(32) NOT NULL,
	range_start BIGINT,
	range_end BIGINT,
	revision INTEGER NOT NULL,
	payload_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_a5da48d80e5aa73be7ac PRIMARY KEY (game_id, idempotency_key),
	CONSTRAINT ck_image_selection_manual_decisions_revision CHECK (revision >= 1),
	CONSTRAINT ck_image_selection_manual_decisions_candidate_resolution CHECK ((resolution IN ('selected_image', 'range_confirmed') AND candidate_id IS NOT NULL) OR (resolution IN ('missing_image', 'duplicate_range', 'rejected_group', 'restored_group') AND candidate_id IS NULL)),
	CONSTRAINT ck_image_selection_manual_decisions_range CHECK ((range_start IS NULL AND range_end IS NULL) OR (range_start >= 1 AND range_end >= range_start)),
	CONSTRAINT ck_image_selection_manual_decisions_resolution CHECK (resolution IN ('selected_image', 'missing_image', 'duplicate_range', 'range_confirmed', 'rejected_group', 'restored_group')),
	CONSTRAINT ck_image_selection_manual_decisions_payload_sha256 CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_0cda62480a1ca85a9638 UNIQUE (game_id, run_id, group_id, revision)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_selection_runs (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	job_id UUID NOT NULL,
	source_selection_id UUID NOT NULL,
	input_manifest_sha256 VARCHAR(64) NOT NULL,
	selector_fingerprint VARCHAR(64) NOT NULL,
	ordering_policy VARCHAR(100) NOT NULL,
	sequence_direction VARCHAR(16) NOT NULL,
	first_sequence_number INTEGER NOT NULL,
	last_sequence_number INTEGER NOT NULL,
	execution_mode VARCHAR(32) NOT NULL,
	source_run_id UUID,
	source_snapshot_sha256 VARCHAR(64),
	contract_version SMALLINT NOT NULL,
	output_manifest_sha256 VARCHAR(64),
	output_manifest_relative_path VARCHAR(1000),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_ebf1c403e1c0aaa93336 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_selection_runs_output_path_safe CHECK (output_manifest_relative_path IS NULL OR (output_manifest_relative_path !~ '(^|/)\.\.(/|$)' AND output_manifest_relative_path !~ '^[A-Za-z]:' AND output_manifest_relative_path NOT LIKE '/%' AND output_manifest_relative_path NOT LIKE '%\\%')),
	CONSTRAINT ck_image_selection_runs_sequence_direction CHECK (sequence_direction IN ('ascending', 'descending')),
	CONSTRAINT ck_image_selection_runs_selector_fingerprint CHECK (selector_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_selection_runs_execution_mode CHECK (execution_mode IN ('full', 'range_recovery')),
	CONSTRAINT ck_image_selection_runs_input_manifest_sha256 CHECK (input_manifest_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_selection_runs_first_sequence_positive CHECK (first_sequence_number >= 0),
	CONSTRAINT ck_image_selection_runs_contract_version CHECK (contract_version = 1),
	CONSTRAINT ck_image_selection_runs_recovery_source CHECK ((execution_mode = 'full' AND source_run_id IS NULL AND source_snapshot_sha256 IS NULL) OR (execution_mode = 'range_recovery' AND source_run_id IS NOT NULL AND source_run_id <> id AND source_snapshot_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_image_selection_runs_last_sequence_positive CHECK (last_sequence_number >= 0),
	CONSTRAINT ck_image_selection_runs_output_manifest_state CHECK ((output_manifest_sha256 IS NULL AND output_manifest_relative_path IS NULL) OR (output_manifest_sha256 ~ '^[0-9a-f]{64}$' AND output_manifest_relative_path IS NOT NULL)),
	CONSTRAINT ck_image_selection_runs_ordering_policy CHECK (ordering_policy = 'natural_relative_path_v1'),
	CONSTRAINT ck_image_selection_runs_sequence_bounds CHECK (last_sequence_number = 0 OR (first_sequence_number > 0 AND ((sequence_direction = 'ascending' AND last_sequence_number >= first_sequence_number) OR (sequence_direction = 'descending' AND last_sequence_number <= first_sequence_number)))),
	CONSTRAINT v2_uq_9d552e618447acb94168 UNIQUE (game_id, job_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_sequence_alternatives (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	import_job_id UUID NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	source_relative_path VARCHAR(1000) NOT NULL,
	reason VARCHAR(50) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_d714b7511171fb6098cf PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_sequence_alternatives_values CHECK (sequence_number > 0 AND source_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_fb82ba502bb152f99b77 UNIQUE (game_id, sequence_number, source_checksum_sha256, import_job_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_sequence_canonical (
	game_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	source_image_id UUID NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	board_checksum_sha256 VARCHAR(64) NOT NULL,
	status VARCHAR(20) NOT NULL,
	resolution_revision INTEGER NOT NULL,
	geometry_revision INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_075a4be69f5c7cff8f01 PRIMARY KEY (game_id, sequence_number),
	CONSTRAINT ck_image_sequence_canonical_values CHECK (sequence_number > 0 AND resolution_revision > 0 AND geometry_revision >= 0),
	CONSTRAINT ck_image_sequence_canonical_checksums CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND board_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_sequence_canonical_status CHECK (status IN ('accepted', 'corrected')),
	CONSTRAINT v2_uq_f47fa30baeb992ea5df5 UNIQUE (game_id, sequence_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_sequence_source_override_events (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	revision INTEGER NOT NULL,
	selected_review_item_id UUID,
	selected_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_1c593c73ab0b722db78b PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_sequence_source_override_sequence_positive CHECK (sequence_number > 0),
	CONSTRAINT ck_image_sequence_source_override_revision_positive CHECK (revision > 0),
	CONSTRAINT v2_uq_5d93474c0b8077f9f1c6 UNIQUE (game_id, sequence_number, revision)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_source_geometry_revisions (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	source_image_id UUID NOT NULL,
	topology_rules_version_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	sequence_range_start BIGINT NOT NULL,
	sequence_range_end BIGINT NOT NULL,
	active_board_slots SMALLINT[] NOT NULL,
	coordinate_space VARCHAR(64) NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	normalized_pixel_checksum_sha256 VARCHAR(64) NOT NULL,
	oriented_width INTEGER NOT NULL,
	oriented_height INTEGER NOT NULL,
	normalization_adapter_version VARCHAR(150) NOT NULL,
	global_initialization JSONB,
	board_geometries JSONB NOT NULL,
	engine_kind VARCHAR(40) NOT NULL,
	engine_version VARCHAR(150) NOT NULL,
	geometry_source VARCHAR(20) NOT NULL,
	status VARCHAR(20) NOT NULL,
	geometry_checksum_sha256 VARCHAR(64) NOT NULL,
	topology_fingerprint_sha256 VARCHAR(64),
	sequence_attestation_schema_version VARCHAR(80),
	sequence_attestation_checksum_sha256 VARCHAR(64),
	processing_time_ms INTEGER,
	warnings JSONB NOT NULL,
	created_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_e2d036c94c9e62d679e9 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_source_geometry_revisions_source CHECK (coordinate_space = 'exif-normalized-rgb-pixels-v1' AND oriented_width > 0 AND oriented_height > 0 AND length(btrim(normalization_adapter_version)) > 0),
	CONSTRAINT ck_image_source_geometry_revisions_engine CHECK (engine_kind IN ('legacy_v20', 'structured_opencv_v1', 'manual_v1', 'keypoint_fallback_v1') AND length(btrim(engine_version)) > 0),
	CONSTRAINT ck_image_source_geometry_revisions_slots CHECK (active_board_slots = (ARRAY[0,1,2,3,4,5,6,7,8]::smallint[])[1:(sequence_range_end - sequence_range_start + 1)::integer]),
	CONSTRAINT ck_image_source_geometry_revisions_state CHECK (geometry_source IN ('auto', 'manual', 'backfill') AND status IN ('pending', 'accepted', 'needs_review', 'rejected') AND (processing_time_ms IS NULL OR processing_time_ms >= 0) AND length(btrim(created_by)) > 0),
	CONSTRAINT ck_image_source_geometry_revisions_checksums CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND normalized_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$' AND geometry_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_source_geometry_revisions_v2_contracts CHECK ((topology_fingerprint_sha256 IS NULL AND sequence_attestation_schema_version IS NULL AND sequence_attestation_checksum_sha256 IS NULL) OR (topology_fingerprint_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(sequence_attestation_schema_version)) > 0 AND sequence_attestation_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_image_source_geometry_revisions_payloads CHECK ((global_initialization IS NULL OR jsonb_typeof(global_initialization) = 'object') AND jsonb_typeof(board_geometries) = 'array' AND jsonb_array_length(board_geometries) = cardinality(active_board_slots) AND jsonb_typeof(warnings) = 'array'),
	CONSTRAINT ck_image_source_geometry_revisions_range CHECK (revision >= 0 AND sequence_range_start > 0 AND sequence_range_end >= sequence_range_start AND sequence_range_end - sequence_range_start + 1 BETWEEN 1 AND 9),
	CONSTRAINT v2_uq_fd29b81bdd3878e81e86 UNIQUE (game_id, source_image_id, geometry_checksum_sha256),
	CONSTRAINT v2_uq_c85a75f72b840d711bac UNIQUE (game_id, source_image_id, revision)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_symbol_prediction_revisions (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	source_job_id UUID NOT NULL,
	model_iteration_id UUID,
	model_version VARCHAR(150) NOT NULL,
	model_checksum_sha256 VARCHAR(64) NOT NULL,
	crop_manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	predictions JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_495aa1afbdfc213ecb7e PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_symbol_prediction_revisions_crop_manifest CHECK (crop_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_symbol_prediction_revisions_model CHECK (length(btrim(model_version)) > 0 AND model_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_b7346e31bb6de280db72 UNIQUE (game_id, review_item_id, model_checksum_sha256, crop_manifest_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_symbol_review_bulk_operations (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	job_id UUID NOT NULL,
	action VARCHAR(30) NOT NULL,
	target_symbol_id UUID,
	selection_kind VARCHAR(20) NOT NULL,
	filter_symbol_id UUID,
	filter_state VARCHAR(20),
	catalog_revision BIGINT,
	idempotency_key UUID NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	actor VARCHAR(200) NOT NULL,
	status VARCHAR(20) NOT NULL,
	target_count BIGINT NOT NULL,
	applied_count BIGINT DEFAULT 0 NOT NULL,
	conflict_count BIGINT DEFAULT 0 NOT NULL,
	failed_count BIGINT DEFAULT 0 NOT NULL,
	error_code VARCHAR(100),
	error_message TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT v2_pk_b3a80047ef77c4d51af7 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_symbol_review_bulk_operations_action CHECK (action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_blurry', 'mark_unreadable')),
	CONSTRAINT ck_image_symbol_review_bulk_operations_status CHECK (status IN ('created', 'processing', 'completed', 'failed', 'cancelled')),
	CONSTRAINT ck_image_symbol_review_bulk_operations_catalog_revision CHECK ((selection_kind = 'filter' AND catalog_revision IS NOT NULL) OR (selection_kind = 'explicit' AND catalog_revision IS NULL)),
	CONSTRAINT ck_image_symbol_review_bulk_operations_selection_kind CHECK (selection_kind IN ('explicit', 'filter')),
	CONSTRAINT ck_image_symbol_review_bulk_operations_counts CHECK (target_count >= 0 AND applied_count >= 0 AND conflict_count >= 0 AND failed_count >= 0 AND applied_count + conflict_count + failed_count <= target_count),
	CONSTRAINT ck_image_symbol_review_bulk_operations_command CHECK (command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_9a2efd9cedf8b09999e8 UNIQUE (game_id, idempotency_key),
	CONSTRAINT v2_uq_b93fbc335c1e937df0bf UNIQUE (game_id, job_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_symbol_review_bulk_targets (
	operation_id UUID NOT NULL,
	cell_review_id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	cell_index SMALLINT NOT NULL,
	expected_revision INTEGER NOT NULL,
	expected_geometry_revision INTEGER NOT NULL,
	expected_crop_sample_id VARCHAR(64) NOT NULL,
	expected_crop_checksum_sha256 VARCHAR(64) NOT NULL,
	status VARCHAR(20) NOT NULL,
	error_code VARCHAR(100),
	error_message TEXT,
	applied_cell_revision INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_bb2389349d70a3d8c6be PRIMARY KEY (game_id, operation_id, cell_review_id),
	CONSTRAINT ck_image_symbol_review_bulk_targets_revisions CHECK (sequence_number > 0 AND cell_index BETWEEN 0 AND 14 AND expected_revision >= 0 AND expected_geometry_revision >= 0),
	CONSTRAINT ck_image_symbol_review_bulk_targets_checksums CHECK (expected_crop_sample_id ~ '^[0-9a-f]{64}$' AND expected_crop_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_symbol_review_bulk_targets_status CHECK (status IN ('pending', 'applied', 'conflict', 'failed'))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_symbol_review_cells (
	source_available BOOLEAN DEFAULT true NOT NULL,
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	cell_index SMALLINT NOT NULL,
	row_index SMALLINT NOT NULL,
	column_index SMALLINT NOT NULL,
	asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	source_geometry_revision_id UUID,
	logical_cell_key VARCHAR(64),
	logical_cell_key_v2 VARCHAR(64),
	render_identity_v2_sha256 VARCHAR(64),
	render_spec JSONB,
	render_spec_checksum_sha256 VARCHAR(64),
	rendered_pixel_checksum_sha256 VARCHAR(64),
	extractor_version VARCHAR(150),
	crop_sample_id VARCHAR(64) NOT NULL,
	crop_relative_path VARCHAR(1000),
	crop_checksum_sha256 VARCHAR(64) NOT NULL,
	geometry_revision INTEGER NOT NULL,
	cropper_version VARCHAR(150) NOT NULL,
	prediction_symbol_code VARCHAR(64),
	prediction_revision_id UUID,
	assigned_symbol_id UUID,
	review_state VARCHAR(20) NOT NULL,
	quality_issue VARCHAR(20),
	verification_outcome VARCHAR(30),
	verified_symbol_id_v2 UUID,
	approved_crop_sample_id VARCHAR(64),
	approved_crop_checksum_sha256 VARCHAR(64),
	approved_geometry_revision INTEGER,
	approved_asset_mode VARCHAR(20),
	approved_source_geometry_revision_id UUID,
	approved_render_spec_checksum_sha256 VARCHAR(64),
	approved_rendered_pixel_checksum_sha256 VARCHAR(64),
	assignment_source VARCHAR(30) NOT NULL,
	revision INTEGER DEFAULT 0 NOT NULL,
	last_reviewed_by VARCHAR(200) NOT NULL,
	last_reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_08b43e8e744ddf461c31 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_symbol_review_cells_source CHECK (assignment_source IN ('model', 'human', 'board_decision', 'backfill')),
	CONSTRAINT ck_image_symbol_review_cells_approved_symbol CHECK (review_state <> 'approved' OR assigned_symbol_id IS NOT NULL OR (quality_issue IS NOT NULL AND quality_issue = 'unreadable')),
	CONSTRAINT ck_image_symbol_review_cells_quality_issue CHECK (quality_issue IS NULL OR quality_issue IN ('grid_issue', 'blurry', 'unreadable')),
	CONSTRAINT ck_image_symbol_review_cells_grid_quality_state CHECK (quality_issue <> 'grid_issue' OR review_state = 'pending'),
	CONSTRAINT ck_image_symbol_review_cells_v2_identity CHECK ((logical_cell_key_v2 IS NULL AND render_identity_v2_sha256 IS NULL) OR (logical_cell_key_v2 ~ '^[0-9a-f]{64}$' AND render_identity_v2_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_image_symbol_review_cells_verification_outcome CHECK ((verification_outcome IS NULL AND verified_symbol_id_v2 IS NULL) OR (verification_outcome IN ('unassigned','unknown','unreadable','grid_issue','requires_review','verified_symbol') AND ((verification_outcome = 'verified_symbol' AND verified_symbol_id_v2 IS NOT NULL) OR (verification_outcome <> 'verified_symbol' AND verified_symbol_id_v2 IS NULL)))),
	CONSTRAINT ck_image_symbol_review_cells_approved_provenance CHECK ((approved_crop_sample_id IS NULL AND approved_crop_checksum_sha256 IS NULL AND approved_geometry_revision IS NULL AND approved_asset_mode IS NULL AND approved_source_geometry_revision_id IS NULL AND approved_render_spec_checksum_sha256 IS NULL AND approved_rendered_pixel_checksum_sha256 IS NULL) OR (approved_crop_sample_id ~ '^[0-9a-f]{64}$' AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' AND approved_geometry_revision >= 0 AND (approved_asset_mode IS NULL OR approved_asset_mode = 'legacy_file') AND approved_source_geometry_revision_id IS NULL AND approved_render_spec_checksum_sha256 IS NULL AND approved_rendered_pixel_checksum_sha256 IS NULL) OR (approved_crop_sample_id ~ '^[0-9a-f]{64}$' AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' AND approved_geometry_revision >= 0 AND approved_asset_mode = 'virtual_source' AND approved_source_geometry_revision_id IS NOT NULL AND approved_render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND approved_rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_image_symbol_review_cells_position CHECK (sequence_number > 0 AND cell_index BETWEEN 0 AND 14 AND row_index BETWEEN 0 AND 2 AND column_index BETWEEN 0 AND 4 AND cell_index = row_index * 5 + column_index),
	CONSTRAINT ck_image_symbol_review_cells_checksums CHECK (crop_sample_id ~ '^[0-9a-f]{64}$' AND crop_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_symbol_review_cells_asset_provenance CHECK ((asset_mode = 'legacy_file' AND length(btrim(crop_relative_path)) > 0 AND crop_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)') OR (asset_mode = 'virtual_source' AND crop_relative_path IS NULL AND source_geometry_revision_id IS NOT NULL AND logical_cell_key ~ '^[0-9a-f]{64}$' AND jsonb_typeof(render_spec) = 'object' AND render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(extractor_version)) > 0)),
	CONSTRAINT ck_image_symbol_review_cells_revisions CHECK (geometry_revision >= 0 AND revision >= 0),
	CONSTRAINT ck_image_symbol_review_cells_state CHECK (review_state IN ('pending', 'approved')),
	CONSTRAINT v2_uq_af8e613c9108abd08084 UNIQUE (game_id, review_item_id, cell_index)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_symbol_review_events (
	id UUID NOT NULL,
	cell_review_id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	logical_cell_key VARCHAR(64),
	previous_logical_cell_key_v2 VARCHAR(64),
	logical_cell_key_v2 VARCHAR(64),
	previous_render_identity_v2_sha256 VARCHAR(64),
	render_identity_v2_sha256 VARCHAR(64),
	previous_asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	previous_source_geometry_revision_id UUID,
	source_geometry_revision_id UUID,
	previous_render_spec_checksum_sha256 VARCHAR(64),
	render_spec_checksum_sha256 VARCHAR(64),
	previous_rendered_pixel_checksum_sha256 VARCHAR(64),
	rendered_pixel_checksum_sha256 VARCHAR(64),
	extractor_version VARCHAR(150),
	crop_sample_id VARCHAR(64) NOT NULL,
	crop_checksum_sha256 VARCHAR(64) NOT NULL,
	geometry_revision INTEGER NOT NULL,
	cell_revision INTEGER NOT NULL,
	action VARCHAR(30) NOT NULL,
	previous_assigned_symbol_id UUID,
	assigned_symbol_id UUID,
	previous_review_state VARCHAR(20) NOT NULL,
	review_state VARCHAR(20) NOT NULL,
	previous_quality_issue VARCHAR(20),
	quality_issue VARCHAR(20),
	previous_verification_outcome VARCHAR(30),
	verification_outcome VARCHAR(30),
	previous_verified_symbol_id_v2 UUID,
	verified_symbol_id_v2 UUID,
	previous_approved_crop_sample_id VARCHAR(64),
	approved_crop_sample_id VARCHAR(64),
	previous_approved_crop_checksum_sha256 VARCHAR(64),
	approved_crop_checksum_sha256 VARCHAR(64),
	previous_approved_geometry_revision INTEGER,
	approved_geometry_revision INTEGER,
	previous_approved_asset_mode VARCHAR(20),
	approved_asset_mode VARCHAR(20),
	previous_approved_source_geometry_revision_id UUID,
	approved_source_geometry_revision_id UUID,
	previous_approved_render_spec_checksum_sha256 VARCHAR(64),
	approved_render_spec_checksum_sha256 VARCHAR(64),
	previous_approved_rendered_pixel_checksum_sha256 VARCHAR(64),
	approved_rendered_pixel_checksum_sha256 VARCHAR(64),
	operation_id UUID,
	actor VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_b10958d3d1b3e46ca476 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_symbol_review_events_render_provenance CHECK ((previous_asset_mode = 'legacy_file' OR (previous_asset_mode = 'virtual_source' AND previous_source_geometry_revision_id IS NOT NULL AND previous_render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND previous_rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$')) AND (asset_mode = 'legacy_file' OR (asset_mode = 'virtual_source' AND source_geometry_revision_id IS NOT NULL AND render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$'))),
	CONSTRAINT ck_image_symbol_review_events_v2_identity CHECK (((previous_logical_cell_key_v2 IS NULL AND previous_render_identity_v2_sha256 IS NULL) OR (previous_logical_cell_key_v2 ~ '^[0-9a-f]{64}$' AND previous_render_identity_v2_sha256 ~ '^[0-9a-f]{64}$')) AND ((logical_cell_key_v2 IS NULL AND render_identity_v2_sha256 IS NULL) OR (logical_cell_key_v2 ~ '^[0-9a-f]{64}$' AND render_identity_v2_sha256 ~ '^[0-9a-f]{64}$'))),
	CONSTRAINT ck_image_symbol_review_events_verification_outcome CHECK (((previous_verification_outcome IS NULL AND previous_verified_symbol_id_v2 IS NULL) OR (previous_verification_outcome IN ('unassigned','unknown','unreadable','grid_issue','requires_review','verified_symbol') AND ((previous_verification_outcome = 'verified_symbol' AND previous_verified_symbol_id_v2 IS NOT NULL) OR (previous_verification_outcome <> 'verified_symbol' AND previous_verified_symbol_id_v2 IS NULL)))) AND ((verification_outcome IS NULL AND verified_symbol_id_v2 IS NULL) OR (verification_outcome IN ('unassigned','unknown','unreadable','grid_issue','requires_review','verified_symbol') AND ((verification_outcome = 'verified_symbol' AND verified_symbol_id_v2 IS NOT NULL) OR (verification_outcome <> 'verified_symbol' AND verified_symbol_id_v2 IS NULL))))),
	CONSTRAINT ck_image_symbol_review_events_checksums CHECK (crop_sample_id ~ '^[0-9a-f]{64}$' AND crop_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_symbol_review_events_action CHECK (action IN ('approve', 'reassign', 'mark_grid_issue', 'mark_blurry', 'mark_unreadable', 'board_synchronized', 'geometry_invalidated')),
	CONSTRAINT ck_image_symbol_review_events_revisions CHECK (geometry_revision >= 0 AND cell_revision >= 0),
	CONSTRAINT ck_image_symbol_review_events_states CHECK (previous_review_state IN ('pending', 'approved') AND review_state IN ('pending', 'approved')),
	CONSTRAINT ck_image_symbol_review_events_quality_issue CHECK ((previous_quality_issue IS NULL OR previous_quality_issue IN ('grid_issue', 'blurry', 'unreadable')) AND (quality_issue IS NULL OR quality_issue IN ('grid_issue', 'blurry', 'unreadable'))),
	CONSTRAINT ck_image_symbol_review_events_approved_crop_identity CHECK ((previous_approved_crop_sample_id IS NULL AND previous_approved_crop_checksum_sha256 IS NULL AND previous_approved_geometry_revision IS NULL) OR (previous_approved_crop_sample_id IS NOT NULL AND previous_approved_crop_checksum_sha256 IS NOT NULL AND previous_approved_geometry_revision IS NOT NULL AND previous_approved_crop_sample_id ~ '^[0-9a-f]{64}$' AND previous_approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' AND previous_approved_geometry_revision >= 0)),
	CONSTRAINT ck_image_symbol_review_events_current_approved_crop_identity CHECK ((approved_crop_sample_id IS NULL AND approved_crop_checksum_sha256 IS NULL AND approved_geometry_revision IS NULL) OR (approved_crop_sample_id IS NOT NULL AND approved_crop_checksum_sha256 IS NOT NULL AND approved_geometry_revision IS NOT NULL AND approved_crop_sample_id ~ '^[0-9a-f]{64}$' AND approved_crop_checksum_sha256 ~ '^[0-9a-f]{64}$' AND approved_geometry_revision >= 0))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_symbol_review_states (
	game_id UUID NOT NULL,
	status VARCHAR(20) NOT NULL,
	processed_review_item_count BIGINT DEFAULT 0 NOT NULL,
	cell_count BIGINT DEFAULT 0 NOT NULL,
	catalog_revision BIGINT DEFAULT 0 NOT NULL,
	missing_sequence_count BIGINT DEFAULT 0 NOT NULL,
	invalid_crop_count BIGINT DEFAULT 0 NOT NULL,
	invalid_geometry_count BIGINT DEFAULT 0 NOT NULL,
	last_review_item_id UUID,
	failure_message VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_cc7017ba1283d89f1d82 PRIMARY KEY (game_id),
	CONSTRAINT ck_image_symbol_review_states_status CHECK (status IN ('rebuilding', 'ready', 'failed')),
	CONSTRAINT ck_image_symbol_review_states_counts CHECK (processed_review_item_count >= 0 AND cell_count >= 0 AND missing_sequence_count >= 0 AND invalid_crop_count >= 0 AND invalid_geometry_count >= 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.image_verified_cohort_exports (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	version INTEGER NOT NULL,
	input_state_sha256 VARCHAR(64) NOT NULL,
	payload_sha256 VARCHAR(64) NOT NULL,
	artifact_relative_path VARCHAR(1000) NOT NULL,
	board_count INTEGER NOT NULL,
	sample_count INTEGER NOT NULL,
	pending_item_count INTEGER NOT NULL,
	rejected_item_count INTEGER NOT NULL,
	created_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_b86f2698aedcfcb88c2b PRIMARY KEY (game_id, id),
	CONSTRAINT ck_image_verified_cohort_exports_sha256 CHECK (input_state_sha256 ~ '^[0-9a-f]{64}$' AND payload_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_image_verified_cohort_exports_counts CHECK (board_count > 0 AND sample_count = board_count * 15 AND pending_item_count >= 0 AND rejected_item_count >= 0),
	CONSTRAINT ck_image_verified_cohort_exports_relative_path CHECK (length(btrim(artifact_relative_path)) > 0 AND artifact_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_image_verified_cohort_exports_version CHECK (version > 0),
	CONSTRAINT v2_uq_0ca0d54399c6276509b4 UNIQUE (game_id, import_job_id, version),
	CONSTRAINT v2_uq_b52dd1f8f26027b5947f UNIQUE (game_id, import_job_id, input_state_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.layout_import_normalized_rows (
	validation_job_id UUID NOT NULL,
	line_number BIGINT NOT NULL,
	import_job_id UUID NOT NULL,
	rules_version_id UUID NOT NULL,
	sequence_number BIGINT,
	cells SMALLINT[],
	signature VARCHAR(500),
	error_code VARCHAR(100),
	error_message VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_50c92a2a58b01f728464 PRIMARY KEY (game_id, validation_job_id, line_number),
	CONSTRAINT ck_layout_import_normalized_rows_sequence_positive CHECK (sequence_number IS NULL OR sequence_number > 0),
	CONSTRAINT ck_layout_import_normalized_rows_cells_not_empty CHECK (cells IS NULL OR cardinality(cells) > 0),
	CONSTRAINT ck_layout_import_normalized_rows_cells_code_range CHECK (cells IS NULL OR (0 <= ALL(cells) AND 32767 >= ALL(cells))),
	CONSTRAINT ck_layout_import_normalized_rows_line_positive CHECK (line_number > 0),
	CONSTRAINT ck_layout_import_normalized_rows_result_variant CHECK ((sequence_number IS NOT NULL AND cells IS NOT NULL AND signature IS NOT NULL AND length(signature) > 0 AND error_code IS NULL AND error_message IS NULL) OR (signature IS NULL AND error_code IS NOT NULL AND error_message IS NOT NULL AND length(btrim(error_code)) > 0 AND length(btrim(error_message)) > 0 AND ((sequence_number IS NULL AND cells IS NULL) OR (sequence_number IS NOT NULL AND cells IS NOT NULL))))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.layout_import_rows (
	job_id UUID NOT NULL,
	line_number BIGINT NOT NULL,
	byte_offset_end BIGINT NOT NULL,
	sequence_number BIGINT,
	cells SMALLINT[],
	error_code VARCHAR(100),
	error_message VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_a5e48b1da552ceb053ce PRIMARY KEY (game_id, job_id, line_number),
	CONSTRAINT ck_layout_import_rows_result_variant CHECK ((sequence_number IS NOT NULL AND cells IS NOT NULL AND error_code IS NULL AND error_message IS NULL) OR (sequence_number IS NULL AND cells IS NULL AND error_code IS NOT NULL AND error_message IS NOT NULL AND length(btrim(error_code)) > 0 AND length(btrim(error_message)) > 0)),
	CONSTRAINT ck_layout_import_rows_cells_not_empty CHECK (cells IS NULL OR cardinality(cells) > 0),
	CONSTRAINT ck_layout_import_rows_line_positive CHECK (line_number > 0),
	CONSTRAINT ck_layout_import_rows_offset_positive CHECK (byte_offset_end > 0),
	CONSTRAINT ck_layout_import_rows_cells_mobile_code_range CHECK (cells IS NULL OR (0 <= ALL(cells) AND 32767 >= ALL(cells))),
	CONSTRAINT ck_layout_import_rows_sequence_positive CHECK (sequence_number IS NULL OR sequence_number > 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.layout_payouts (
	dataset_version_id UUID NOT NULL,
	rules_version_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	algorithm_version VARCHAR(100) NOT NULL,
	total_payout BIGINT NOT NULL,
	audit_path VARCHAR(1000),
	calculated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_a5d0866eeedde3b5b531 PRIMARY KEY (game_id, dataset_version_id, rules_version_id, sequence_number, algorithm_version),
	CONSTRAINT ck_layout_payouts_algorithm_not_blank CHECK (length(btrim(algorithm_version)) > 0),
	CONSTRAINT ck_layout_payouts_total_nonnegative CHECK (total_payout >= 0),
	CONSTRAINT ck_layout_payouts_audit_path_not_blank CHECK (audit_path IS NULL OR length(btrim(audit_path)) > 0),
	CONSTRAINT ck_layout_payouts_sequence_positive CHECK (sequence_number > 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.layouts (
	id BIGSERIAL NOT NULL,
	dataset_version_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	signature VARCHAR NOT NULL,
	cells SMALLINT[] NOT NULL,
	source_board_id UUID,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_7c31f497d1da5b02bb27 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_layouts_cells_mobile_code_range CHECK (0 <= ALL(cells) AND 32767 >= ALL(cells)),
	CONSTRAINT ck_layouts_cells_not_empty CHECK (cardinality(cells) > 0),
	CONSTRAINT ck_layouts_sequence_number_positive CHECK (sequence_number > 0),
	CONSTRAINT v2_uq_a494c8b8664012ffe0fb UNIQUE (game_id, dataset_version_id, sequence_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.legacy_board_search_archive_documents (
	game_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	status VARCHAR(20) NOT NULL,
	board_relative_path VARCHAR(1000) NOT NULL,
	board_checksum_sha256 VARCHAR(64) NOT NULL,
	known_evidence_positions VARCHAR(2)[] NOT NULL,
	primary_symbol_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_1_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_2_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_3_mobile_codes SMALLINT[] NOT NULL,
	alternative_rank_4_mobile_codes SMALLINT[] NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_507132f4de98d7d71f78 PRIMARY KEY (game_id, sequence_number),
	CONSTRAINT ck_legacy_board_search_archive_documents_path CHECK (length(btrim(board_relative_path)) > 0 AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_legacy_board_search_archive_documents_status CHECK (status IN ('pending', 'accepted', 'corrected')),
	CONSTRAINT ck_legacy_board_search_archive_documents_sequence_positive CHECK (sequence_number > 0),
	CONSTRAINT ck_legacy_board_search_archive_documents_checksum CHECK (board_checksum_sha256 ~ '^[0-9a-f]{64}$')
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.legacy_board_search_archive_states (
	game_id UUID NOT NULL,
	status VARCHAR(20) NOT NULL,
	sequence_start BIGINT NOT NULL,
	sequence_end BIGINT NOT NULL,
	document_count BIGINT NOT NULL,
	source_preview_fingerprint VARCHAR(64) NOT NULL,
	archive_fingerprint VARCHAR(64) NOT NULL,
	failure_message VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_dcbf8f1e1300641626cc PRIMARY KEY (game_id),
	CONSTRAINT ck_legacy_board_search_archive_states_status CHECK (status IN ('building', 'ready', 'failed')),
	CONSTRAINT ck_legacy_board_search_archive_states_fingerprints CHECK (source_preview_fingerprint ~ '^[0-9a-f]{64}$' AND archive_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_legacy_board_search_archive_states_range CHECK (sequence_start > 0 AND sequence_end >= sequence_start AND document_count >= 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.mobile_release_games (
	mobile_release_id UUID NOT NULL,
	game_id UUID NOT NULL,
	dataset_version_id UUID NOT NULL,
	rules_version_id UUID NOT NULL,
	layout_count BIGINT NOT NULL,
	CONSTRAINT v2_pk_fcd7988d81e7422ae4f3 PRIMARY KEY (game_id, mobile_release_id),
	CONSTRAINT ck_mobile_release_games_layout_count_positive CHECK (layout_count > 0)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.recognized_boards (
	id UUID NOT NULL,
	source_image_id UUID NOT NULL,
	position_index SMALLINT NOT NULL,
	sequence_number_raw VARCHAR(100) NOT NULL,
	sequence_number BIGINT,
	sequence_confidence FLOAT NOT NULL,
	board_geometry JSONB NOT NULL,
	asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	source_geometry_revision_id UUID,
	geometry_engine_name VARCHAR(80),
	geometry_engine_version VARCHAR(150),
	geometry_checksum_sha256 VARCHAR(64),
	board_relative_path VARCHAR(1000),
	board_checksum_sha256 VARCHAR(64),
	cells_prediction JSONB NOT NULL,
	completeness_status VARCHAR(24) DEFAULT 'complete' NOT NULL,
	geometry_qualification JSONB,
	unavailable_cell_indices SMALLINT[] DEFAULT '{}' NOT NULL,
	board_confidence FLOAT NOT NULL,
	pipeline_fingerprint VARCHAR(64) NOT NULL,
	geometry_revision INTEGER DEFAULT 0 NOT NULL,
	grid_rows SMALLINT,
	grid_columns SMALLINT,
	approved_geometry_revision INTEGER,
	geometry_approved_at TIMESTAMP WITH TIME ZONE,
	geometry_approved_by VARCHAR(200),
	status VARCHAR(30) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_e6550bb4cfba7d4ac0d9 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_recognized_boards_grid_topology CHECK ((grid_rows IS NULL AND grid_columns IS NULL) OR (grid_rows IS NOT NULL AND grid_columns IS NOT NULL AND grid_rows > 0 AND grid_columns > 0)),
	CONSTRAINT ck_recognized_boards_status CHECK (status IN ('pending_review', 'accepted', 'corrected', 'rejected')),
	CONSTRAINT ck_recognized_boards_geometry_approval_revision CHECK (approved_geometry_revision IS NULL OR (approved_geometry_revision >= 0 AND approved_geometry_revision <= geometry_revision)),
	CONSTRAINT ck_recognized_boards_confidence CHECK (sequence_confidence BETWEEN 0 AND 1 AND board_confidence BETWEEN 0 AND 1),
	CONSTRAINT ck_recognized_boards_completeness CHECK ((completeness_status = 'complete' AND cardinality(unavailable_cell_indices) = 0) OR (completeness_status = 'pending_partial' AND cardinality(unavailable_cell_indices) BETWEEN 1 AND 15 AND unavailable_cell_indices <@ ARRAY[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]::smallint[])),
	CONSTRAINT ck_recognized_boards_geometry_approval_metadata CHECK ((approved_geometry_revision IS NULL AND geometry_approved_at IS NULL AND geometry_approved_by IS NULL) OR (approved_geometry_revision IS NOT NULL AND geometry_approved_at IS NOT NULL AND geometry_approved_by IS NOT NULL AND length(btrim(geometry_approved_by)) > 0)),
	CONSTRAINT ck_recognized_boards_pipeline_checksum CHECK (pipeline_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_recognized_boards_geometry_revision CHECK (geometry_revision >= 0),
	CONSTRAINT ck_recognized_boards_sequence_positive CHECK (sequence_number IS NULL OR sequence_number > 0),
	CONSTRAINT ck_recognized_boards_qualification CHECK (geometry_qualification IS NULL OR ((jsonb_typeof(geometry_qualification) = 'object' AND ((geometry_qualification->>'version' = 'manual-geometry-qualification-v1' AND NOT (geometry_qualification ? 'includeInPartialGridTraining')) OR (geometry_qualification->>'version' = 'manual-geometry-qualification-v2' AND jsonb_typeof(geometry_qualification->'includeInPartialGridTraining') = 'boolean')) AND geometry_qualification->>'completenessStatus' = completeness_status AND geometry_qualification->'unavailableCellIndices' = to_jsonb(unavailable_cell_indices) AND ((completeness_status = 'pending_partial' AND geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'missing_pixels') OR (completeness_status = 'complete' AND COALESCE(geometry_qualification->'includeInPartialGridTraining', 'false'::jsonb) = 'false'::jsonb AND ((geometry_qualification->'excludeFromGeometryTraining' = 'true'::jsonb AND geometry_qualification->>'exclusionReason' = 'manual_exclusion') OR (geometry_qualification->'excludeFromGeometryTraining' = 'false'::jsonb AND geometry_qualification->'exclusionReason' = 'null'::jsonb))))) IS TRUE)),
	CONSTRAINT ck_recognized_boards_position CHECK (position_index BETWEEN 0 AND 8),
	CONSTRAINT ck_recognized_boards_asset_provenance CHECK ((asset_mode = 'legacy_file' AND board_checksum_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(board_relative_path)) > 0 AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)') OR (asset_mode = 'virtual_source' AND board_relative_path IS NULL AND board_checksum_sha256 IS NULL AND source_geometry_revision_id IS NOT NULL AND length(btrim(geometry_engine_name)) > 0 AND length(btrim(geometry_engine_version)) > 0 AND geometry_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT v2_uq_3422589609390c1ef4be UNIQUE (game_id, source_image_id, position_index)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.representative_ranking_activations (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	iteration_id UUID NOT NULL,
	previous_iteration_id UUID,
	action VARCHAR(20) NOT NULL,
	activation_number INTEGER NOT NULL,
	actor VARCHAR(200) NOT NULL,
	reason TEXT,
	idempotency_key UUID NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_39a2f8ef0c44777264ea PRIMARY KEY (game_id, id),
	CONSTRAINT ck_representative_ranking_activations_values CHECK (action IN ('activate','rollback') AND activation_number > 0),
	CONSTRAINT ck_representative_ranking_activations_checksum CHECK (command_sha256 ~ '^[0-9a-f]{64}$' AND btrim(actor) <> ''),
	CONSTRAINT v2_uq_5b72172e1fd02b1f2ecc UNIQUE (game_id, idempotency_key),
	CONSTRAINT v2_uq_e36376e6293fe8c492c2 UNIQUE (game_id, activation_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.representative_ranking_cohorts (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	iteration_number INTEGER NOT NULL,
	manifest_schema_version INTEGER NOT NULL,
	manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	positive_count INTEGER NOT NULL,
	pair_count INTEGER NOT NULL,
	excluded_ambiguous_count INTEGER NOT NULL,
	folder_count INTEGER NOT NULL,
	group_count INTEGER NOT NULL,
	artifact_relative_path VARCHAR(1000) NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_8c39578c6ffefae0b89a PRIMARY KEY (game_id, id),
	CONSTRAINT ck_representative_ranking_cohorts_versions CHECK (iteration_number > 0 AND manifest_schema_version > 0),
	CONSTRAINT ck_representative_ranking_cohorts_counts CHECK (positive_count >= 0 AND pair_count >= 0 AND excluded_ambiguous_count >= 0 AND folder_count >= 0 AND group_count >= 0),
	CONSTRAINT ck_representative_ranking_cohorts_checksum CHECK (manifest_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_df1d6a743e0a6bdaea05 UNIQUE (game_id, manifest_checksum_sha256),
	CONSTRAINT v2_uq_b5b298bf9cb608b52d27 UNIQUE (game_id, iteration_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.representative_ranking_iterations (
	id UUID NOT NULL,
	cohort_id UUID NOT NULL,
	feature_version VARCHAR(100) NOT NULL,
	model_version VARCHAR(100) NOT NULL,
	model_checksum_sha256 VARCHAR(64) NOT NULL,
	model_artifact_relative_path VARCHAR(1000) NOT NULL,
	report JSONB NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_b77c59fdb2875087e538 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_representative_ranking_iterations_values CHECK (feature_version <> '' AND model_version <> '' AND btrim(status) <> ''),
	CONSTRAINT ck_representative_ranking_iterations_checksum CHECK (model_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_dc931768c6de7ca9ac5d UNIQUE (game_id, cohort_id, model_checksum_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.review_batches (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	source_report_sha256 VARCHAR(64) NOT NULL,
	active_learning_version VARCHAR(100) NOT NULL,
	model_version VARCHAR(100) NOT NULL,
	model_artifact_sha256 VARCHAR(64) NOT NULL,
	calibration_report_sha256 VARCHAR(64) NOT NULL,
	dataset_sha256 VARCHAR(64) NOT NULL,
	split_sha256 VARCHAR(64) NOT NULL,
	inventory_sha256 VARCHAR(64) NOT NULL,
	temperature FLOAT NOT NULL,
	item_count SMALLINT NOT NULL,
	source_report JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_529da9f2ab1ebe15dbcc PRIMARY KEY (game_id, id),
	CONSTRAINT ck_review_batches_item_count CHECK (item_count BETWEEN 1 AND 100),
	CONSTRAINT ck_review_batches_source_report_sha256 CHECK (source_report_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_review_batches_provenance_sha256 CHECK (model_artifact_sha256 ~ '^[0-9a-f]{64}$' AND calibration_report_sha256 ~ '^[0-9a-f]{64}$' AND dataset_sha256 ~ '^[0-9a-f]{64}$' AND split_sha256 ~ '^[0-9a-f]{64}$' AND inventory_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_review_batches_temperature_positive CHECK (temperature > 0),
	CONSTRAINT v2_uq_6bbf4c8779dbf64cb5dc UNIQUE (game_id, source_report_sha256)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.review_feedback_exports (
	id UUID NOT NULL,
	review_batch_id UUID NOT NULL,
	game_id UUID NOT NULL,
	version INTEGER NOT NULL,
	source_state_sha256 VARCHAR(64) NOT NULL,
	payload_sha256 VARCHAR(64) NOT NULL,
	sample_count INTEGER NOT NULL,
	rejected_item_count INTEGER NOT NULL,
	payload JSONB NOT NULL,
	created_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_81aa4489b6e27c852089 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_review_feedback_exports_sha256 CHECK (source_state_sha256 ~ '^[0-9a-f]{64}$' AND payload_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_review_feedback_exports_counts CHECK (sample_count >= 0 AND rejected_item_count >= 0),
	CONSTRAINT ck_review_feedback_exports_version_positive CHECK (version > 0),
	CONSTRAINT v2_uq_c27bdfb92115a50af235 UNIQUE (game_id, review_batch_id, source_state_sha256),
	CONSTRAINT v2_uq_41a76da6cc6d58770664 UNIQUE (game_id, version)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.review_items (
	id UUID NOT NULL,
	review_batch_id UUID NOT NULL,
	board_id VARCHAR(64) NOT NULL,
	selection_rank SMALLINT NOT NULL,
	sequence_number BIGINT NOT NULL,
	source_image_id VARCHAR(200) NOT NULL,
	source_image_checksum_sha256 VARCHAR(64) NOT NULL,
	source_group VARCHAR(200) NOT NULL,
	board_relative_path VARCHAR(1000) NOT NULL,
	status review_item_status NOT NULL,
	prediction_snapshot JSONB NOT NULL,
	resolved_value JSONB,
	resolved_by VARCHAR(200),
	resolved_at TIMESTAMP WITH TIME ZONE,
	resolution_revision INTEGER DEFAULT 0 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_bfd75806b4cf2e37fc9c PRIMARY KEY (game_id, id),
	CONSTRAINT ck_review_items_selection_rank CHECK (selection_rank BETWEEN 1 AND 100),
	CONSTRAINT ck_review_items_resolution_state CHECK ((status = 'pending' AND resolved_value IS NULL AND resolved_by IS NULL AND resolved_at IS NULL AND resolution_revision = 0) OR (status <> 'pending' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL AND resolution_revision > 0)),
	CONSTRAINT ck_review_items_sequence_positive CHECK (sequence_number > 0),
	CONSTRAINT ck_review_items_board_path_safe CHECK (length(btrim(board_relative_path)) > 0 AND board_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_review_items_identity_sha256 CHECK (board_id ~ '^[0-9a-f]{64}$' AND source_image_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_f3b7a3764dc951bfc4b2 UNIQUE (game_id, review_batch_id, board_id),
	CONSTRAINT v2_uq_de94863a94881f2ce918 UNIQUE (game_id, review_batch_id, selection_rank),
	CONSTRAINT v2_uq_32428acaa443ad4a34cb UNIQUE (game_id, review_batch_id, sequence_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.review_resolutions (
	id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	idempotency_key UUID NOT NULL,
	action review_resolution_action NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	resolved_value JSONB NOT NULL,
	resolved_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_2632fd3c5a203ea23785 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_review_resolutions_revision_positive CHECK (revision > 0),
	CONSTRAINT ck_review_resolutions_command_sha256 CHECK (command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_467e38bbb9275f75b04c UNIQUE (game_id, review_item_id, idempotency_key),
	CONSTRAINT v2_uq_1b752d7f4f413f449b83 UNIQUE (game_id, review_item_id, revision)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.reviewer_access_audit_events (
	id UUID NOT NULL,
	session_id UUID NOT NULL,
	event_type VARCHAR(32) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_08fdc434437f75349054 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_reviewer_access_audit_events_type CHECK (event_type IN ('created', 'unlock_failed', 'unlocked', 'locked', 'revoked'))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.reviewer_access_sessions (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	code_salt BYTEA NOT NULL,
	code_hash BYTEA NOT NULL,
	failed_attempts SMALLINT NOT NULL,
	locked_at TIMESTAMP WITH TIME ZONE,
	revoked_at TIMESTAMP WITH TIME ZONE,
	token_hash BYTEA,
	token_expires_at TIMESTAMP WITH TIME ZONE,
	last_unlocked_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT v2_pk_ace667abba2e8037eab2 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_reviewer_access_sessions_failed_attempts CHECK (failed_attempts BETWEEN 0 AND 5),
	CONSTRAINT ck_reviewer_access_sessions_expiration CHECK (expires_at > created_at),
	CONSTRAINT v2_uq_20ddc1c1110e189246af UNIQUE (game_id, id, import_job_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.reviewer_work_assignments (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	assignment_type VARCHAR(16) NOT NULL,
	reviewer_access_session_id UUID,
	lease_owner VARCHAR(200) NOT NULL,
	lease_token UUID NOT NULL,
	heartbeat_at TIMESTAMP WITH TIME ZONE NOT NULL,
	lease_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	closed_at TIMESTAMP WITH TIME ZONE,
	close_reason VARCHAR(100),
	closed_by VARCHAR(200),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_1e11906b5f10fdbab5d6 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_reviewer_work_assignments_lease_timestamps CHECK (heartbeat_at >= created_at AND lease_expires_at > heartbeat_at AND updated_at >= heartbeat_at),
	CONSTRAINT ck_reviewer_work_assignments_closure CHECK ((closed_at IS NULL AND close_reason IS NULL AND closed_by IS NULL) OR (closed_at IS NOT NULL AND closed_at >= heartbeat_at AND close_reason IS NOT NULL AND closed_by IS NOT NULL AND length(btrim(close_reason)) BETWEEN 1 AND 100 AND length(btrim(closed_by)) BETWEEN 1 AND 200)),
	CONSTRAINT ck_reviewer_work_assignments_type CHECK (assignment_type IN ('local', 'online')),
	CONSTRAINT ck_reviewer_work_assignments_lease_owner CHECK (length(btrim(lease_owner)) BETWEEN 1 AND 200),
	CONSTRAINT ck_reviewer_work_assignments_session_mode CHECK ((assignment_type = 'local' AND reviewer_access_session_id IS NULL) OR (assignment_type = 'online' AND reviewer_access_session_id IS NOT NULL))
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.source_images (
	id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	file_execution_key VARCHAR(64) NOT NULL,
	relative_path VARCHAR(1000) NOT NULL,
	checksum_sha256 VARCHAR(64) NOT NULL,
	width INTEGER NOT NULL,
	height INTEGER NOT NULL,
	raw_width INTEGER,
	raw_height INTEGER,
	oriented_width INTEGER,
	oriented_height INTEGER,
	exif_orientation SMALLINT,
	coordinate_space VARCHAR(64),
	normalization_adapter_version VARCHAR(150),
	normalized_pixel_checksum_sha256 VARCHAR(64),
	status VARCHAR(30) NOT NULL,
	error_code VARCHAR(100),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	processed_at TIMESTAMP WITH TIME ZONE,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_437a7eeb64c3a2d1124f PRIMARY KEY (game_id, id),
	CONSTRAINT ck_source_images_relative_path CHECK (length(btrim(relative_path)) > 0 AND relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_source_images_coordinate_metadata CHECK ((raw_width IS NULL AND raw_height IS NULL AND oriented_width IS NULL AND oriented_height IS NULL AND exif_orientation IS NULL AND coordinate_space IS NULL AND normalization_adapter_version IS NULL AND normalized_pixel_checksum_sha256 IS NULL) OR (raw_width > 0 AND raw_height > 0 AND oriented_width > 0 AND oriented_height > 0 AND (exif_orientation IS NULL OR exif_orientation BETWEEN 1 AND 8) AND coordinate_space = 'exif-normalized-rgb-pixels-v1' AND length(btrim(normalization_adapter_version)) > 0 AND normalized_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_source_images_dimensions_positive CHECK (width > 0 AND height > 0),
	CONSTRAINT ck_source_images_status CHECK (status IN ('discovered', 'processing', 'waiting_for_review', 'accepted', 'rejected', 'completed', 'failed')),
	CONSTRAINT ck_source_images_checksum CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_b13dbd41b5c046115e25 UNIQUE (game_id, import_job_id, checksum_sha256),
	CONSTRAINT v2_uq_83e8399b2d8f193f2d09 UNIQUE (game_id, import_job_id, file_execution_key)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.symbol_model_iterations (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	cohort_id UUID NOT NULL,
	job_id UUID NOT NULL,
	iteration_number INTEGER NOT NULL,
	status VARCHAR(30) NOT NULL,
	configuration_fingerprint VARCHAR(64) NOT NULL,
	configuration_payload JSONB NOT NULL,
	dataset_manifest_checksum_sha256 VARCHAR(64),
	dataset_manifest_relative_path VARCHAR(1000),
	checkpoint_checksum_sha256 VARCHAR(64),
	checkpoint_relative_path VARCHAR(1000),
	gate_configuration_fingerprint VARCHAR(64),
	gate_configuration_payload JSONB,
	candidate_manifest_checksum_sha256 VARCHAR(64),
	candidate_manifest_relative_path VARCHAR(1000),
	gate_report_checksum_sha256 VARCHAR(64),
	gate_report_relative_path VARCHAR(1000),
	gate_metrics JSONB NOT NULL,
	rejection_reasons VARCHAR(100)[] NOT NULL,
	last_completed_epoch INTEGER NOT NULL,
	partial_metrics JSONB NOT NULL,
	error_code VARCHAR(100),
	error_message TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_1774689f99b6effc0083 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_symbol_model_iterations_sha256 CHECK (configuration_fingerprint ~ '^[0-9a-f]{64}$' AND (dataset_manifest_checksum_sha256 IS NULL OR dataset_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$') AND (checkpoint_checksum_sha256 IS NULL OR checkpoint_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_symbol_model_iterations_status CHECK (status IN ('created','dataset_build','training','trained','evaluating','candidate_ready','rejected','failed','cancelled')),
	CONSTRAINT ck_symbol_model_iterations_gate_sha256 CHECK ((gate_configuration_fingerprint IS NULL OR gate_configuration_fingerprint ~ '^[0-9a-f]{64}$') AND (candidate_manifest_checksum_sha256 IS NULL OR candidate_manifest_checksum_sha256 ~ '^[0-9a-f]{64}$') AND (gate_report_checksum_sha256 IS NULL OR gate_report_checksum_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_symbol_model_iterations_numbers CHECK (iteration_number > 0 AND last_completed_epoch >= 0),
	CONSTRAINT v2_uq_c362c1d4a2b46d35ef7e UNIQUE (game_id, job_id),
	CONSTRAINT v2_uq_beda59f8c868d660e03b UNIQUE (game_id, cohort_id, configuration_fingerprint),
	CONSTRAINT v2_uq_c6e9b3716e62c7d66219 UNIQUE (game_id, iteration_number)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.symbol_reference_images (
	symbol_id UUID NOT NULL,
	game_id UUID NOT NULL,
	source_review_item_id UUID NOT NULL,
	source_recognized_board_id UUID NOT NULL,
	source_observation_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	cell_index SMALLINT NOT NULL,
	resolution_revision INTEGER NOT NULL,
	geometry_revision INTEGER NOT NULL,
	image_relative_path VARCHAR(1000) NOT NULL,
	image_checksum_sha256 VARCHAR(64) NOT NULL,
	selected_by VARCHAR(200) NOT NULL,
	selected_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_0bd7f95397f5a32cf444 PRIMARY KEY (game_id, symbol_id),
	CONSTRAINT ck_symbol_reference_images_position CHECK (sequence_number > 0 AND cell_index BETWEEN 0 AND 14 AND resolution_revision >= 0 AND geometry_revision >= 0),
	CONSTRAINT ck_symbol_reference_images_relative_path CHECK (length(btrim(image_relative_path)) > 0 AND image_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT ck_symbol_reference_images_checksum CHECK (image_checksum_sha256 ~ '^[0-9a-f]{64}$')
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.verified_training_cohort_cells (
	id UUID NOT NULL,
	cohort_id UUID NOT NULL,
	sample_order INTEGER NOT NULL,
	cell_review_id UUID NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	source_image_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	cell_index SMALLINT NOT NULL,
	symbol_code VARCHAR(64) NOT NULL,
	asset_mode VARCHAR(20) DEFAULT 'legacy_file' NOT NULL,
	source_geometry_revision_id UUID,
	logical_cell_key VARCHAR(64),
	logical_cell_key_v2 VARCHAR(64),
	render_identity_v2_sha256 VARCHAR(64),
	render_spec JSONB,
	render_spec_checksum_sha256 VARCHAR(64),
	rendered_pixel_checksum_sha256 VARCHAR(64),
	extractor_version VARCHAR(150),
	crop_checksum_sha256 VARCHAR(64) NOT NULL,
	sample_checksum_sha256 VARCHAR(64) NOT NULL,
	cell_manifest JSONB NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_9c1e4035ac0014931895 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_verified_training_cohort_cells_asset_provenance CHECK (asset_mode = 'legacy_file' OR (asset_mode = 'virtual_source' AND source_geometry_revision_id IS NOT NULL AND logical_cell_key ~ '^[0-9a-f]{64}$' AND jsonb_typeof(render_spec) = 'object' AND render_spec_checksum_sha256 ~ '^[0-9a-f]{64}$' AND rendered_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$' AND length(btrim(extractor_version)) > 0)),
	CONSTRAINT ck_verified_training_cohort_cells_manifest CHECK (jsonb_typeof(cell_manifest) = 'object'),
	CONSTRAINT ck_verified_training_cohort_cells_position CHECK (sample_order >= 0 AND sequence_number > 0 AND cell_index BETWEEN 0 AND 14),
	CONSTRAINT ck_verified_training_cohort_cells_v2_identity CHECK ((logical_cell_key_v2 IS NULL AND render_identity_v2_sha256 IS NULL) OR (logical_cell_key_v2 ~ '^[0-9a-f]{64}$' AND render_identity_v2_sha256 ~ '^[0-9a-f]{64}$')),
	CONSTRAINT ck_verified_training_cohort_cells_checksums CHECK (sample_checksum_sha256 ~ '^[0-9a-f]{64}$' AND crop_checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT v2_uq_7c644926a3b6dad91e16 UNIQUE (game_id, cohort_id, cell_review_id),
	CONSTRAINT v2_uq_5c09f1e84add69f2b6ad UNIQUE (game_id, cohort_id, sample_order)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.verified_training_cohort_items (
	id UUID NOT NULL,
	cohort_id UUID NOT NULL,
	item_order INTEGER NOT NULL,
	review_item_id UUID NOT NULL,
	recognized_board_id UUID NOT NULL,
	source_image_id UUID NOT NULL,
	import_job_id UUID NOT NULL,
	sequence_number BIGINT NOT NULL,
	decision_status VARCHAR(20) NOT NULL,
	resolution_revision INTEGER NOT NULL,
	geometry_revision INTEGER NOT NULL,
	source_checksum_sha256 VARCHAR(64) NOT NULL,
	board_checksum_sha256 VARCHAR(64) NOT NULL,
	pipeline_fingerprint VARCHAR(64) NOT NULL,
	item_checksum_sha256 VARCHAR(64) NOT NULL,
	board_manifest JSONB NOT NULL,
	game_id UUID NOT NULL,
	CONSTRAINT v2_pk_1340ae3d61b51b3b4b35 PRIMARY KEY (game_id, id),
	CONSTRAINT ck_verified_training_cohort_items_manifest CHECK (jsonb_typeof(board_manifest) = 'object' AND jsonb_array_length(board_manifest -> 'cells') = 15),
	CONSTRAINT ck_verified_training_cohort_items_values CHECK (item_order >= 0 AND sequence_number > 0 AND resolution_revision > 0 AND geometry_revision >= 0),
	CONSTRAINT ck_verified_training_cohort_items_sha256 CHECK (item_checksum_sha256 ~ '^[0-9a-f]{64}$' AND source_checksum_sha256 ~ '^[0-9a-f]{64}$' AND board_checksum_sha256 ~ '^[0-9a-f]{64}$' AND pipeline_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_verified_training_cohort_items_status CHECK (decision_status IN ('accepted', 'corrected')),
	CONSTRAINT v2_uq_c1d5c9f9349102d6576e UNIQUE (game_id, cohort_id, item_order),
	CONSTRAINT v2_uq_a5b2a06a226632b36206 UNIQUE (game_id, cohort_id, review_item_id)
)
 PARTITION BY LIST (game_id);

CREATE TABLE game_data_v2.verified_training_cohorts (
	id UUID NOT NULL,
	game_id UUID NOT NULL,
	iteration_number INTEGER NOT NULL,
	manifest_schema_version INTEGER NOT NULL,
	dataset_kind VARCHAR(100) NOT NULL,
	manifest_checksum_sha256 VARCHAR(64) NOT NULL,
	idempotency_key UUID NOT NULL,
	command_sha256 VARCHAR(64) NOT NULL,
	resolved_layout_count INTEGER NOT NULL,
	cell_sample_count INTEGER NOT NULL,
	source_image_count INTEGER NOT NULL,
	pending_item_count INTEGER NOT NULL,
	rejected_item_count INTEGER NOT NULL,
	incomplete_item_count INTEGER NOT NULL,
	artifact_relative_path VARCHAR(1000) NOT NULL,
	created_by VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT v2_pk_267d20c22cc1f8e343bc PRIMARY KEY (game_id, id),
	CONSTRAINT ck_verified_training_cohorts_counts CHECK (resolved_layout_count > 0 AND cell_sample_count > 0 AND source_image_count > 0 AND pending_item_count >= 0 AND rejected_item_count >= 0 AND incomplete_item_count >= 0),
	CONSTRAINT ck_verified_training_cohorts_sha256 CHECK (manifest_checksum_sha256 ~ '^[0-9a-f]{64}$' AND command_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_verified_training_cohorts_versions CHECK (iteration_number > 0 AND manifest_schema_version > 0),
	CONSTRAINT ck_verified_training_cohorts_relative_path CHECK (length(btrim(artifact_relative_path)) > 0 AND artifact_relative_path !~ '(^/|(^|/)\.\.(/|$)|\\)'),
	CONSTRAINT v2_uq_3ac311a78912f8027dea UNIQUE (game_id, manifest_checksum_sha256),
	CONSTRAINT v2_uq_a32996956554ae60594d UNIQUE (game_id, iteration_number),
	CONSTRAINT v2_uq_358923ccd42bef6b9546 UNIQUE (game_id, idempotency_key)
)
 PARTITION BY LIST (game_id);

CREATE INDEX v2_fkix_1cbcf9b0adabac4e4039 ON game_data_v2.browser_selection_retention_states (game_id, import_job_id);

CREATE INDEX v2_fkix_afc419584177cff54753 ON game_data_v2.browser_selection_retention_states (game_id);

CREATE INDEX v2_ix_16e4ce34ebd00db55415 ON game_data_v2.browser_selection_retention_states (game_id, state, eligible_at);

CREATE INDEX v2_fkix_31e45cdd09309d4ecee8 ON game_data_v2.cell_observations (game_id, recognized_board_id);

CREATE INDEX v2_fkix_75be5e8580565020adab ON game_data_v2.cell_observations (game_id, source_geometry_revision_id);

CREATE INDEX v2_ix_50e330c8623e89211948 ON game_data_v2.cell_observations (game_id, logical_cell_key, source_geometry_revision_id) WHERE logical_cell_key IS NOT NULL;

CREATE INDEX v2_fkix_550234c647c2459a0dbb ON game_data_v2.curated_image_import_batches (game_id, job_id);

CREATE INDEX v2_fkix_d7c43705058b9bb40859 ON game_data_v2.curated_image_import_batches (game_id, source_id);

CREATE INDEX v2_ix_b6f2b1eb26eb348cc13f ON game_data_v2.curated_image_import_batches (game_id, source_id, created_at);

CREATE INDEX v2_fkix_471f2e0a32c248cd4a18 ON game_data_v2.curated_image_import_sources (game_id, image_selection_run_id);

CREATE INDEX v2_fkix_b6857af431a1933a9d84 ON game_data_v2.curated_image_import_sources (game_id);

CREATE INDEX v2_ix_6c6b9d7405ac540d9d0f ON game_data_v2.curated_image_import_sources (game_id, created_at);

CREATE INDEX v2_fkix_8cdc016d78b665b0a87c ON game_data_v2.dataset_versions (game_id, source_job_id);

CREATE INDEX v2_fkix_f092cdad371ec337daf5 ON game_data_v2.dataset_versions (game_id);

CREATE UNIQUE INDEX v2_ix_7233a01ce71f0d6dad5b ON game_data_v2.dataset_versions (game_id, source_job_id) WHERE source_job_id IS NOT NULL;

CREATE INDEX v2_ix_8ba57b1d3808393b0ee6 ON game_data_v2.dataset_versions (game_id);

CREATE INDEX v2_fkix_0c9fa0940a2317a39c7c ON game_data_v2.game_grid_profile_activations (game_id);

CREATE INDEX v2_fkix_125316b01f4da3cea7ff ON game_data_v2.game_grid_profile_activations (game_id, previous_profile_id);

CREATE INDEX v2_fkix_fcde7e590ff8c10c53c9 ON game_data_v2.game_grid_profile_activations (game_id, profile_id);

CREATE INDEX v2_ix_0307a51d4aa36a75637a ON game_data_v2.game_grid_profile_activations (game_id, activation_number);

CREATE INDEX v2_fkix_7826c2c8ff99937f6e98 ON game_data_v2.game_symbol_model_activations (game_id, model_iteration_id);

CREATE INDEX v2_fkix_840fe3f958ccc168613c ON game_data_v2.game_symbol_model_activations (game_id);

CREATE INDEX v2_fkix_f37ddd41c92cd62ddb1c ON game_data_v2.game_symbol_model_activations (game_id, previous_model_iteration_id);

CREATE INDEX v2_ix_975e00e97cb48ebe4e16 ON game_data_v2.game_symbol_model_activations (game_id, activation_number);

CREATE INDEX v2_fkix_56930a63fb4df52e02da ON game_data_v2.grid_calibration_profiles (game_id);

CREATE INDEX v2_fkix_b2ba0fb1fd0640752009 ON game_data_v2.grid_calibration_profiles (game_id, cohort_id);

CREATE INDEX v2_ix_ec4f7739cefddf32e7c9 ON game_data_v2.grid_calibration_profiles (game_id, status);

CREATE INDEX v2_fkix_4cae779509d44d127dac ON game_data_v2.grid_geometry_cohorts (game_id);

CREATE INDEX v2_ix_788cd91e501fd198e991 ON game_data_v2.grid_geometry_cohorts (game_id, created_at);

CREATE INDEX v2_fkix_43bd0f44112e1406b098 ON game_data_v2.image_board_geometry_pending (game_id, source_image_id);

CREATE INDEX v2_fkix_49e0e1b4a1675bdca9bc ON game_data_v2.image_board_geometry_pending (game_id);

CREATE INDEX v2_fkix_9271ed4a32559e3ca384 ON game_data_v2.image_board_geometry_pending (game_id, recognized_board_id);

CREATE INDEX v2_fkix_e2b2e245b6bb54805757 ON game_data_v2.image_board_geometry_pending (game_id, review_item_id);

CREATE INDEX v2_fkix_f15ef7d9b335f94d8f42 ON game_data_v2.image_board_geometry_pending (game_id, import_job_id);

CREATE INDEX v2_ix_a5b7fde1615d294952b7 ON game_data_v2.image_board_geometry_pending (game_id, import_job_id, status, sequence_number, position_index, id);

CREATE UNIQUE INDEX v2_ix_f50c3272650155186815 ON game_data_v2.image_board_geometry_pending (game_id, import_job_id, source_image_id, position_index) WHERE status = 'pending';

CREATE INDEX v2_fkix_364433199cb7271b5112 ON game_data_v2.image_board_geometry_review_events (game_id, recognized_board_id);

CREATE INDEX v2_fkix_e0ba53f5b3462d8697aa ON game_data_v2.image_board_geometry_review_events (game_id, review_item_id);

CREATE INDEX v2_ix_03ddbba480a248ef55aa ON game_data_v2.image_board_geometry_review_events (game_id, recognized_board_id, created_at);

CREATE INDEX v2_fkix_2d9b3a358b2f83cb0db7 ON game_data_v2.image_board_geometry_revisions (game_id, review_item_id);

CREATE INDEX v2_fkix_745aef4c7467937e84d6 ON game_data_v2.image_board_geometry_revisions (game_id, source_geometry_revision_id);

CREATE INDEX v2_fkix_fc2f3f863514d11e7971 ON game_data_v2.image_board_geometry_revisions (game_id, recognized_board_id);

CREATE INDEX v2_fkix_1dac2d1a94450d538ada ON game_data_v2.image_board_search_candidates (game_id);

CREATE INDEX v2_fkix_397847c7bd2234944985 ON game_data_v2.image_board_search_candidates (game_id, review_item_id);

CREATE INDEX v2_fkix_982a176a5576258f40e3 ON game_data_v2.image_board_search_candidates (game_id, recognized_board_id);

CREATE INDEX v2_fkix_b219e8d5f3e0b03ea121 ON game_data_v2.image_board_search_candidates (game_id, import_job_id);

CREATE INDEX v2_ix_4bda45a068a2b731dd31 ON game_data_v2.image_board_search_candidates (game_id, sequence_number);

CREATE INDEX v2_ix_b9e7ca2e80a5f84a6def ON game_data_v2.image_board_search_candidates (game_id, status, sequence_number);

CREATE INDEX v2_fkix_a4e43b06e452fbc9aa60 ON game_data_v2.image_board_search_fast_documents (game_id, review_item_id);

CREATE INDEX v2_fkix_e93169ad735df74053d7 ON game_data_v2.image_board_search_fast_documents (game_id);

CREATE INDEX v2_fkix_3896f9a3f0cdb5aaec75 ON game_data_v2.image_board_search_projection_states (game_id);

CREATE INDEX v2_fkix_2a1a14ed4c0683f7f970 ON game_data_v2.image_geometry_rollout_states (game_id);

CREATE INDEX v2_fkix_89a9dd07436a0a94e8e8 ON game_data_v2.image_geometry_rollout_states (game_id, validation_job_id);

CREATE INDEX v2_fkix_e078a76ed5992834a358 ON game_data_v2.image_geometry_rollout_states (game_id, last_source_image_id);

CREATE INDEX v2_ix_9f6f0739d216d36f1d37 ON game_data_v2.image_geometry_rollout_states (game_id, geometry_mode, cell_asset_mode);

CREATE INDEX v2_fkix_2d906b315050c502f895 ON game_data_v2.image_import_geometry_guard_decisions (game_id);

CREATE INDEX v2_fkix_35ef41a273ab4f31ba83 ON game_data_v2.image_import_geometry_guard_decisions (game_id, browser_selection_id);

CREATE INDEX v2_fkix_cf06e7908e9c6221988c ON game_data_v2.image_import_geometry_guard_decisions (game_id, guard_job_id);

CREATE INDEX v2_ix_18b60678644d017d098f ON game_data_v2.image_import_geometry_guard_decisions (game_id, guard_job_id, source_checksum_sha256, position_index, revision);

CREATE INDEX v2_fkix_1e36c2753e05de31e34b ON game_data_v2.image_import_geometry_guard_resolution_manifests (game_id);

CREATE INDEX v2_fkix_23f12b428eb9e9f74a70 ON game_data_v2.image_import_geometry_guard_resolution_manifests (game_id, guard_job_id);

CREATE INDEX v2_fkix_63df5ae968e77143cb9c ON game_data_v2.image_import_geometry_guard_resolution_manifests (game_id, browser_selection_id);

CREATE INDEX v2_ix_0277681eb2de2adfce6f ON game_data_v2.image_import_geometry_guard_resolution_manifests (game_id, guard_job_id, created_at);

CREATE INDEX v2_fkix_14a0c9ae5a5412afa745 ON game_data_v2.image_import_job_files (file_execution_key);

CREATE INDEX v2_fkix_4d743cfe563650cf36c7 ON game_data_v2.image_import_job_files (game_id, job_id);

CREATE INDEX v2_ix_a590055d9c7717ee144a ON game_data_v2.image_import_job_files (game_id, job_id, workflow_status, order_index);

CREATE INDEX v2_ix_e293e9815301a55b8de4 ON game_data_v2.image_import_job_files (game_id, file_execution_key);

CREATE INDEX v2_fkix_16feb976eabdfc8972ce ON game_data_v2.image_layout_staging_rows (game_id, import_job_id);

CREATE INDEX v2_fkix_6f9c15c9a75aa6e86e53 ON game_data_v2.image_layout_staging_rows (game_id, recognized_board_id);

CREATE INDEX v2_fkix_a3512093422497db7bb1 ON game_data_v2.image_layout_staging_rows (game_id, review_item_id);

CREATE INDEX v2_ix_6e55206f094291607a1a ON game_data_v2.image_layout_staging_rows (game_id, import_job_id, sequence_number);

CREATE INDEX v2_fkix_ff24c7b25e8faa4f1ee4 ON game_data_v2.image_page_geometry_overrides (game_id);

CREATE INDEX v2_ix_6f009c25f9fa869c27da ON game_data_v2.image_page_geometry_overrides (game_id, source_checksum_sha256, revision);

CREATE INDEX v2_fkix_ae889dd4103401f36e7a ON game_data_v2.image_page_source_exclusions (game_id, browser_selection_id);

CREATE INDEX v2_fkix_e7f00fe1c532dc05dbc4 ON game_data_v2.image_page_source_exclusions (game_id);

CREATE INDEX v2_ix_85de46fc46220b75fe69 ON game_data_v2.image_page_source_exclusions (game_id, browser_selection_id, source_checksum_sha256);

CREATE INDEX v2_fkix_018543dfbe47ce8c3626 ON game_data_v2.image_review_items (game_id, import_job_id);

CREATE INDEX v2_fkix_bf21a5c695ae4f7aa049 ON game_data_v2.image_review_items (game_id, recognized_board_id);

CREATE INDEX v2_fkix_ee8970537f6ebb37be73 ON game_data_v2.image_review_items (game_id);

CREATE INDEX v2_ix_580d0aabd955da3e9569 ON game_data_v2.image_review_items (game_id, import_job_id, status);

CREATE UNIQUE INDEX v2_ix_5fc39a775558f0d5d83b ON game_data_v2.image_review_items (game_id, sequence_number) WHERE status = 'pending' AND sequence_number IS NOT NULL;

CREATE INDEX v2_fkix_56924abfb3cc0499143a ON game_data_v2.image_review_queue_items (game_id, import_job_id);

CREATE INDEX v2_fkix_bfe0a764f651cc2315ac ON game_data_v2.image_review_queue_items (game_id, review_item_id);

CREATE INDEX v2_ix_2bec72c610b084cbee1e ON game_data_v2.image_review_queue_items (game_id, import_job_id, status, source_order_index, position_index, review_item_id);

CREATE INDEX v2_fkix_53952384789f2c5ea581 ON game_data_v2.image_review_queue_states (game_id, import_job_id);

CREATE INDEX v2_fkix_348731797fa3265dd3b8 ON game_data_v2.image_review_resolution_events (game_id, review_item_id);

CREATE INDEX v2_fkix_19b03727ca4ad627acd8 ON game_data_v2.image_selection_candidates (game_id, run_id, group_id);

CREATE INDEX v2_fkix_cf752b95f284f552df78 ON game_data_v2.image_selection_candidates (game_id, run_id);

CREATE UNIQUE INDEX v2_ix_4510873a44eada0af7b3 ON game_data_v2.image_selection_candidates (game_id, run_id, group_id) WHERE decision IN ('selected_automatic', 'selected_manual');

CREATE INDEX v2_ix_ea7b501b4d6eedc2ebcc ON game_data_v2.image_selection_candidates (game_id, run_id, group_id, order_index);

CREATE INDEX v2_fkix_326760382d4ef6fff7b1 ON game_data_v2.image_selection_groups (game_id, run_id);

CREATE INDEX v2_fkix_93a5e08f8bd887d0fc21 ON game_data_v2.image_selection_groups (game_id, origin_group_id);

CREATE UNIQUE INDEX v2_ix_4e559d5c74ebafe13509 ON game_data_v2.image_selection_groups (game_id, run_id, range_start, range_end) WHERE status IN ('auto_selected', 'manually_selected', 'missing_image', 'range_confirmed') AND range_start IS NOT NULL;

CREATE INDEX v2_ix_63e5efef0d434e7fed28 ON game_data_v2.image_selection_groups (game_id, origin_group_id);

CREATE INDEX v2_fkix_0daf160f21adc5906082 ON game_data_v2.image_selection_manual_decisions (game_id, run_id, group_id);

CREATE INDEX v2_fkix_5871e2f489e46ae88807 ON game_data_v2.image_selection_manual_decisions (game_id, candidate_id);

CREATE INDEX v2_fkix_9f5281e72593d0b19402 ON game_data_v2.image_selection_manual_decisions (game_id, run_id);

CREATE INDEX v2_ix_873f90976869a0f3ede6 ON game_data_v2.image_selection_manual_decisions (game_id, run_id, group_id, revision);

CREATE INDEX v2_fkix_02628d4eef2d6ad3398a ON game_data_v2.image_selection_runs (game_id);

CREATE INDEX v2_fkix_1507b4c802feb27e9a06 ON game_data_v2.image_selection_runs (game_id, job_id);

CREATE INDEX v2_fkix_a274e44b516d71d5790c ON game_data_v2.image_selection_runs (game_id, source_run_id);

CREATE INDEX v2_ix_19f9967ce5ff4f060915 ON game_data_v2.image_selection_runs (game_id, source_selection_id);

CREATE INDEX v2_ix_1e64c67bbf90b3ea7835 ON game_data_v2.image_selection_runs (game_id, created_at);

CREATE UNIQUE INDEX v2_ix_3356cf8a9664d783578d ON game_data_v2.image_selection_runs (game_id, input_manifest_sha256, selector_fingerprint, sequence_direction, first_sequence_number, last_sequence_number) WHERE execution_mode = 'full';

CREATE INDEX v2_ix_4b423476c2ed8112baf8 ON game_data_v2.image_selection_runs (game_id, source_run_id);

CREATE UNIQUE INDEX v2_ix_cd3134d4eb0ec3a8112f ON game_data_v2.image_selection_runs (game_id, source_run_id, selector_fingerprint, source_snapshot_sha256, last_sequence_number) WHERE execution_mode = 'range_recovery';

CREATE INDEX v2_fkix_4a9afe118674f97b29bb ON game_data_v2.image_sequence_alternatives (game_id);

CREATE INDEX v2_fkix_4bc94236a8cd0244b83d ON game_data_v2.image_sequence_alternatives (game_id, import_job_id);

CREATE INDEX v2_ix_f647c2a9b416e2762dcd ON game_data_v2.image_sequence_alternatives (game_id, sequence_number);

CREATE INDEX v2_fkix_30a4c2875e48dc911776 ON game_data_v2.image_sequence_canonical (game_id);

CREATE INDEX v2_fkix_4968eb6802d044661959 ON game_data_v2.image_sequence_canonical (game_id, source_image_id);

CREATE INDEX v2_fkix_4ce66cce1df7a3020090 ON game_data_v2.image_sequence_canonical (game_id, import_job_id);

CREATE INDEX v2_fkix_53ec306b94375df5bf42 ON game_data_v2.image_sequence_canonical (game_id, recognized_board_id);

CREATE INDEX v2_fkix_70154b79d00a81b0b0ff ON game_data_v2.image_sequence_canonical (game_id, review_item_id);

CREATE INDEX v2_ix_38427c7069c260ccb141 ON game_data_v2.image_sequence_canonical (game_id, sequence_number);

CREATE INDEX v2_fkix_857675ba219cb341058f ON game_data_v2.image_sequence_source_override_events (game_id, selected_review_item_id);

CREATE INDEX v2_fkix_b9ab2d24d7c2a3f6279a ON game_data_v2.image_sequence_source_override_events (game_id);

CREATE INDEX v2_ix_bbd23120f4a61334abf9 ON game_data_v2.image_sequence_source_override_events (game_id, sequence_number, revision);

CREATE INDEX v2_fkix_0cd8a24555f45901370a ON game_data_v2.image_source_geometry_revisions (game_id, topology_rules_version_id);

CREATE INDEX v2_fkix_81bb5c389f3c24fe51bf ON game_data_v2.image_source_geometry_revisions (game_id, source_image_id);

CREATE INDEX v2_fkix_820f8b2b2bfa27e63b71 ON game_data_v2.image_source_geometry_revisions (game_id);

CREATE INDEX v2_ix_05537c01b286ed64c166 ON game_data_v2.image_source_geometry_revisions (game_id, source_image_id, created_at);

CREATE INDEX v2_ix_82723b026fc7c669bbd8 ON game_data_v2.image_source_geometry_revisions (game_id, status, created_at);

CREATE INDEX v2_fkix_a39a59b243d1928ea1c6 ON game_data_v2.image_symbol_prediction_revisions (game_id, source_job_id);

CREATE INDEX v2_fkix_a7758792b2db8d98b414 ON game_data_v2.image_symbol_prediction_revisions (game_id, review_item_id);

CREATE INDEX v2_fkix_cedac91148c948dfa3dd ON game_data_v2.image_symbol_prediction_revisions (game_id, recognized_board_id);

CREATE INDEX v2_fkix_f4f81cb2eb82f22c43e0 ON game_data_v2.image_symbol_prediction_revisions (game_id, model_iteration_id);

CREATE INDEX v2_fkix_f7937020763b6cd6ad02 ON game_data_v2.image_symbol_prediction_revisions (game_id);

CREATE INDEX v2_ix_1fca27c9cdbed2b6cd74 ON game_data_v2.image_symbol_prediction_revisions (game_id, review_item_id, created_at);

CREATE INDEX v2_fkix_1a1ea3b18692e939e91d ON game_data_v2.image_symbol_review_bulk_operations (game_id);

CREATE INDEX v2_fkix_5f0db50668f52af2bc70 ON game_data_v2.image_symbol_review_bulk_operations (game_id, filter_symbol_id);

CREATE INDEX v2_fkix_c6d7c917648ed7fe1402 ON game_data_v2.image_symbol_review_bulk_operations (game_id, job_id);

CREATE INDEX v2_fkix_dbcfae6218fac353b73f ON game_data_v2.image_symbol_review_bulk_operations (game_id, target_symbol_id);

CREATE INDEX v2_ix_e7318ea361322b512609 ON game_data_v2.image_symbol_review_bulk_operations (game_id, status, created_at, id);

CREATE INDEX v2_fkix_198c22c290bb008bd1e7 ON game_data_v2.image_symbol_review_bulk_targets (game_id, recognized_board_id);

CREATE INDEX v2_fkix_4b798377b2de6246546c ON game_data_v2.image_symbol_review_bulk_targets (game_id, cell_review_id);

CREATE INDEX v2_fkix_a716ebc1aaaecc332f72 ON game_data_v2.image_symbol_review_bulk_targets (game_id, review_item_id);

CREATE INDEX v2_fkix_c8333010cf40723255aa ON game_data_v2.image_symbol_review_bulk_targets (game_id, operation_id);

CREATE INDEX v2_ix_bf89cf1189221b891faf ON game_data_v2.image_symbol_review_bulk_targets (game_id, operation_id, sequence_number, review_item_id, cell_index);

CREATE INDEX v2_ix_c0a8c0914c44e77f7948 ON game_data_v2.image_symbol_review_bulk_targets (game_id, operation_id, status, review_item_id);

CREATE INDEX v2_fkix_0e5970aa21879e7384bd ON game_data_v2.image_symbol_review_cells (game_id, approved_source_geometry_revision_id);

CREATE INDEX v2_fkix_7913fda68b24dca91690 ON game_data_v2.image_symbol_review_cells (game_id, source_geometry_revision_id);

CREATE INDEX v2_fkix_84659059f8c09f577281 ON game_data_v2.image_symbol_review_cells (game_id, verified_symbol_id_v2);

CREATE INDEX v2_fkix_8d85362d62b5f696b081 ON game_data_v2.image_symbol_review_cells (game_id, assigned_symbol_id);

CREATE INDEX v2_fkix_8dcccaae262a7dea7047 ON game_data_v2.image_symbol_review_cells (game_id, import_job_id);

CREATE INDEX v2_fkix_8fa558a43895130f256e ON game_data_v2.image_symbol_review_cells (game_id, prediction_revision_id);

CREATE INDEX v2_fkix_9745dc600a9897bd6226 ON game_data_v2.image_symbol_review_cells (game_id);

CREATE INDEX v2_fkix_b15df8e35ee3ebb8467b ON game_data_v2.image_symbol_review_cells (game_id, recognized_board_id);

CREATE INDEX v2_fkix_e98b5d1da7c890232451 ON game_data_v2.image_symbol_review_cells (game_id, review_item_id);

CREATE INDEX v2_ix_14328d2a62fdbe0eb708 ON game_data_v2.image_symbol_review_cells (game_id, assigned_symbol_id, sequence_number, cell_index, review_item_id);

CREATE INDEX v2_ix_1b48daab20c3b7504fb3 ON game_data_v2.image_symbol_review_cells (game_id, review_item_id, cell_index) WHERE quality_issue = 'grid_issue';

CREATE INDEX v2_ix_3cde7e9baac971e009bf ON game_data_v2.image_symbol_review_cells (game_id, review_item_id, cell_index) WHERE quality_issue = 'unreadable';

CREATE INDEX v2_ix_4f514c0fb95dd5f5d0f3 ON game_data_v2.image_symbol_review_cells (game_id, prediction_revision_id);

CREATE INDEX v2_ix_6958affb30ece9d608a4 ON game_data_v2.image_symbol_review_cells (game_id, sequence_number, cell_index, review_item_id);

CREATE INDEX v2_ix_89d14c2bb2aa5f0b7086 ON game_data_v2.image_symbol_review_cells (game_id, assigned_symbol_id, review_state, sequence_number, cell_index, review_item_id);

CREATE INDEX v2_fkix_2619e99a526e5e2058f6 ON game_data_v2.image_symbol_review_events (game_id, review_item_id);

CREATE INDEX v2_fkix_27da886793c4b9cb0f74 ON game_data_v2.image_symbol_review_events (game_id, verified_symbol_id_v2);

CREATE INDEX v2_fkix_2e92779b97a25c916590 ON game_data_v2.image_symbol_review_events (game_id, previous_approved_source_geometry_revision_id);

CREATE INDEX v2_fkix_3ccfc7c82027e35fcc78 ON game_data_v2.image_symbol_review_events (game_id, cell_review_id);

CREATE INDEX v2_fkix_46a13b8a2664a6c84954 ON game_data_v2.image_symbol_review_events (game_id, previous_verified_symbol_id_v2);

CREATE INDEX v2_fkix_7be4ef9ee4c02b271d7d ON game_data_v2.image_symbol_review_events (game_id, approved_source_geometry_revision_id);

CREATE INDEX v2_fkix_835975875a27bfe888cd ON game_data_v2.image_symbol_review_events (game_id, source_geometry_revision_id);

CREATE INDEX v2_fkix_a110540a73bd0fa4b8c3 ON game_data_v2.image_symbol_review_events (game_id, assigned_symbol_id);

CREATE INDEX v2_fkix_aa44eb1c669503500ee7 ON game_data_v2.image_symbol_review_events (game_id, previous_source_geometry_revision_id);

CREATE INDEX v2_fkix_b683f61cd6b3a9bd9394 ON game_data_v2.image_symbol_review_events (game_id, operation_id);

CREATE INDEX v2_fkix_e976144b0786165954b9 ON game_data_v2.image_symbol_review_events (game_id, previous_assigned_symbol_id);

CREATE INDEX v2_ix_ca4b9d9f540ec2d98652 ON game_data_v2.image_symbol_review_events (game_id, review_item_id, created_at);

CREATE INDEX v2_ix_ed4e3f57bf3901263752 ON game_data_v2.image_symbol_review_events (game_id, cell_review_id, created_at);

CREATE INDEX v2_fkix_4c076c4a047e9b18bced ON game_data_v2.image_symbol_review_states (game_id);

CREATE INDEX v2_fkix_70ad5030f35bee637aef ON game_data_v2.image_verified_cohort_exports (game_id);

CREATE INDEX v2_fkix_b0ebcc1cee29381972d1 ON game_data_v2.image_verified_cohort_exports (game_id, import_job_id);

CREATE INDEX v2_fkix_0c50e0ddfc7d9984dd8a ON game_data_v2.layout_import_normalized_rows (game_id, rules_version_id);

CREATE INDEX v2_fkix_929edce408e008d6b9b8 ON game_data_v2.layout_import_normalized_rows (game_id, validation_job_id);

CREATE INDEX v2_fkix_c95c40d1ea039046a65b ON game_data_v2.layout_import_normalized_rows (game_id, import_job_id, line_number);

CREATE INDEX v2_ix_07ba00ff07b15f90e7ee ON game_data_v2.layout_import_normalized_rows (game_id, validation_job_id, sequence_number);

CREATE INDEX v2_ix_bad6d9dcc35026123f5d ON game_data_v2.layout_import_normalized_rows (game_id, validation_job_id, signature);

CREATE INDEX v2_fkix_dc0842121b51674b90b4 ON game_data_v2.layout_import_rows (game_id, job_id);

CREATE INDEX v2_ix_d91b1994506a5e56fccf ON game_data_v2.layout_import_rows (game_id, job_id, byte_offset_end);

CREATE INDEX v2_fkix_4f3339c375e04b6644d3 ON game_data_v2.layout_payouts (game_id, dataset_version_id, sequence_number);

CREATE INDEX v2_fkix_8aa040e253a34c75f3b8 ON game_data_v2.layout_payouts (game_id, rules_version_id);

CREATE INDEX v2_ix_864cbb6e1cf0c51ea7c1 ON game_data_v2.layout_payouts (game_id, rules_version_id);

CREATE INDEX v2_fkix_1194501f3f4add8f02b5 ON game_data_v2.layouts (game_id, dataset_version_id);

CREATE INDEX v2_ix_433b7ec72abef9f71457 ON game_data_v2.layouts (game_id, dataset_version_id);

CREATE INDEX v2_ix_a70ed08761906b8010b0 ON game_data_v2.layouts (game_id, dataset_version_id, signature);

CREATE INDEX v2_fkix_6e59f056870c4bc0aeee ON game_data_v2.legacy_board_search_archive_documents (game_id);

CREATE INDEX v2_fkix_7b05b27370ba0b53cc0f ON game_data_v2.legacy_board_search_archive_states (game_id);

CREATE INDEX v2_fkix_31a93b20626acd512af1 ON game_data_v2.mobile_release_games (mobile_release_id);

CREATE INDEX v2_fkix_905a8dd4246bce5100cf ON game_data_v2.mobile_release_games (game_id, dataset_version_id);

CREATE INDEX v2_fkix_dfd8dd2a683edd7f6527 ON game_data_v2.mobile_release_games (game_id);

CREATE INDEX v2_fkix_fad81eef3492214474b1 ON game_data_v2.mobile_release_games (game_id, rules_version_id);

CREATE INDEX v2_ix_46a1602925c8db08edf2 ON game_data_v2.mobile_release_games (game_id);

CREATE INDEX v2_fkix_9199f9ba9457342673ad ON game_data_v2.recognized_boards (game_id, source_image_id);

CREATE INDEX v2_fkix_a4123004f6e718770de0 ON game_data_v2.recognized_boards (game_id, source_geometry_revision_id);

CREATE INDEX v2_ix_15c8d079cdf682d3e3eb ON game_data_v2.recognized_boards (game_id, source_image_id, status);

CREATE INDEX v2_ix_20300acd8aa9069d6c66 ON game_data_v2.recognized_boards (game_id, source_geometry_revision_id, position_index);

CREATE INDEX v2_ix_c264dec175d534891f98 ON game_data_v2.recognized_boards (game_id, geometry_revision, approved_geometry_revision, id);

CREATE INDEX v2_fkix_446cd2f534402d776559 ON game_data_v2.representative_ranking_activations (game_id, iteration_id);

CREATE INDEX v2_fkix_fb596f610be88f4e5121 ON game_data_v2.representative_ranking_activations (game_id);

CREATE INDEX v2_fkix_fd724de640a2f002e3aa ON game_data_v2.representative_ranking_activations (game_id, previous_iteration_id);

CREATE INDEX v2_ix_eb6a4fad9e71ae673298 ON game_data_v2.representative_ranking_activations (game_id, created_at);

CREATE INDEX v2_fkix_f9987f2b1ed96391f33f ON game_data_v2.representative_ranking_cohorts (game_id);

CREATE INDEX v2_ix_7a2741862085f755ef3c ON game_data_v2.representative_ranking_cohorts (game_id, created_at);

CREATE INDEX v2_fkix_2fec48bf1b5a5f1c24ee ON game_data_v2.representative_ranking_iterations (game_id, cohort_id);

CREATE INDEX v2_ix_dd2793919a3d4807b6e9 ON game_data_v2.representative_ranking_iterations (game_id, cohort_id, created_at);

CREATE INDEX v2_fkix_eed7d541318fcac93835 ON game_data_v2.review_batches (game_id);

CREATE INDEX v2_fkix_7911ea0ea7cb0f84048b ON game_data_v2.review_feedback_exports (game_id);

CREATE INDEX v2_fkix_af8ff20e42ae9a38d221 ON game_data_v2.review_feedback_exports (game_id, review_batch_id);

CREATE INDEX v2_fkix_1dfe1b2038dde5db0c01 ON game_data_v2.review_items (game_id, review_batch_id);

CREATE INDEX v2_ix_4241aa993875a7ce5b9e ON game_data_v2.review_items (game_id, review_batch_id, status, selection_rank);

CREATE INDEX v2_fkix_4e11caf4b120ea46b5fc ON game_data_v2.review_resolutions (game_id, review_item_id);

CREATE INDEX v2_ix_fab252d17eaff24d3cf3 ON game_data_v2.review_resolutions (game_id, review_item_id, revision);

CREATE INDEX v2_fkix_510188a794702536c358 ON game_data_v2.reviewer_access_audit_events (game_id, session_id);

CREATE INDEX v2_ix_705e91a7bf8cacfb7c91 ON game_data_v2.reviewer_access_audit_events (game_id, session_id, created_at);

CREATE INDEX v2_fkix_66015ea970057adba2c5 ON game_data_v2.reviewer_access_sessions (game_id, import_job_id);

CREATE INDEX v2_fkix_e14c0a22b2ab91fbd546 ON game_data_v2.reviewer_access_sessions (game_id);

CREATE INDEX v2_ix_0b3d47798d730bcc322e ON game_data_v2.reviewer_access_sessions (game_id, import_job_id);

CREATE UNIQUE INDEX v2_ix_2c7d3cb09b690eadb152 ON game_data_v2.reviewer_access_sessions (game_id, token_hash);

CREATE INDEX v2_ix_abcd3445f8baadd10886 ON game_data_v2.reviewer_access_sessions (game_id);

CREATE INDEX v2_fkix_04ca9bb47a7a1086a942 ON game_data_v2.reviewer_work_assignments (game_id);

CREATE INDEX v2_fkix_390ac14771a653473bc6 ON game_data_v2.reviewer_work_assignments (game_id, import_job_id);

CREATE INDEX v2_fkix_5b9f37158aaeafb6639c ON game_data_v2.reviewer_work_assignments (game_id, reviewer_access_session_id, import_job_id);

CREATE UNIQUE INDEX v2_ix_09be419ea7383dfc261a ON game_data_v2.reviewer_work_assignments (game_id, reviewer_access_session_id) WHERE reviewer_access_session_id IS NOT NULL;

CREATE INDEX v2_ix_7dc092727d378d689867 ON game_data_v2.reviewer_work_assignments (game_id, import_job_id, created_at, id);

CREATE UNIQUE INDEX v2_ix_fa8cf5eef7574f8e7690 ON game_data_v2.reviewer_work_assignments (game_id, import_job_id) WHERE closed_at IS NULL;

CREATE INDEX v2_ix_fc0cb9919effe5718332 ON game_data_v2.reviewer_work_assignments (game_id, lease_expires_at, import_job_id) WHERE closed_at IS NULL;

CREATE INDEX v2_fkix_90fdac1fbbd0c39bb681 ON game_data_v2.source_images (game_id, import_job_id);

CREATE INDEX v2_fkix_cf6ada333f55f3a8bcde ON game_data_v2.source_images (file_execution_key);

CREATE INDEX v2_ix_0ce2e7cc8d6cf22bacca ON game_data_v2.source_images (game_id, import_job_id, status);

CREATE INDEX v2_fkix_0361090277892a5c8f25 ON game_data_v2.symbol_model_iterations (game_id, cohort_id);

CREATE INDEX v2_fkix_24d62a38fcef3b0aeefd ON game_data_v2.symbol_model_iterations (game_id, job_id);

CREATE INDEX v2_fkix_4dc1499544ab8fb73894 ON game_data_v2.symbol_model_iterations (game_id);

CREATE INDEX v2_ix_10d70fb13b6b37604b3f ON game_data_v2.symbol_model_iterations (game_id, status);

CREATE INDEX v2_fkix_657ff3d6c526545fcfa6 ON game_data_v2.symbol_reference_images (game_id, source_observation_id);

CREATE INDEX v2_fkix_76dfa9fecb7b6403afcc ON game_data_v2.symbol_reference_images (game_id, source_review_item_id);

CREATE INDEX v2_fkix_7746675b9b0fccf88d11 ON game_data_v2.symbol_reference_images (game_id);

CREATE INDEX v2_fkix_b56c4fe7c61158a79eca ON game_data_v2.symbol_reference_images (game_id, source_recognized_board_id);

CREATE INDEX v2_fkix_e6c8d462f3fbcc4389d4 ON game_data_v2.symbol_reference_images (game_id, symbol_id);

CREATE INDEX v2_ix_c37474051a94966174b5 ON game_data_v2.symbol_reference_images (game_id);

CREATE INDEX v2_fkix_24c55f0b72c652d543ba ON game_data_v2.verified_training_cohort_cells (game_id, cell_review_id);

CREATE INDEX v2_fkix_2c7a1d975fd782c65aff ON game_data_v2.verified_training_cohort_cells (game_id, source_geometry_revision_id);

CREATE INDEX v2_fkix_4d8e08f81ab865d4152c ON game_data_v2.verified_training_cohort_cells (game_id, review_item_id);

CREATE INDEX v2_fkix_80b1d38f31fa0df5dca9 ON game_data_v2.verified_training_cohort_cells (game_id, source_image_id);

CREATE INDEX v2_fkix_c3c20039cbf032bad935 ON game_data_v2.verified_training_cohort_cells (game_id, cohort_id);

CREATE INDEX v2_fkix_de3de36a82b656d85001 ON game_data_v2.verified_training_cohort_cells (game_id, recognized_board_id);

CREATE INDEX v2_ix_91b7914f0767a0efc470 ON game_data_v2.verified_training_cohort_cells (game_id, cohort_id, symbol_code);

CREATE INDEX v2_fkix_724b66189ea3cfafb8bb ON game_data_v2.verified_training_cohort_items (game_id, source_image_id);

CREATE INDEX v2_fkix_73783c41d4f6f5457cc3 ON game_data_v2.verified_training_cohort_items (game_id, import_job_id);

CREATE INDEX v2_fkix_83c8ce867c7d965e3ed6 ON game_data_v2.verified_training_cohort_items (game_id, review_item_id);

CREATE INDEX v2_fkix_9a094658ddbb58970464 ON game_data_v2.verified_training_cohort_items (game_id, cohort_id);

CREATE INDEX v2_fkix_fe572123b42ae4abd712 ON game_data_v2.verified_training_cohort_items (game_id, recognized_board_id);

CREATE INDEX v2_fkix_e1374a322744746cc45f ON game_data_v2.verified_training_cohorts (game_id);

ALTER TABLE game_data_v2.browser_selection_retention_states ADD CONSTRAINT v2_fk_1cbcf9b0adabac4e4039 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.browser_selection_retention_states ADD CONSTRAINT v2_fk_afc419584177cff54753 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.cell_observations ADD CONSTRAINT v2_fk_31e45cdd09309d4ecee8 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.cell_observations ADD CONSTRAINT v2_fk_75be5e8580565020adab FOREIGN KEY(game_id, source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.cell_observations ADD CONSTRAINT v2_owner_f08239a9ad51dd216330 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.curated_image_import_batches ADD CONSTRAINT v2_fk_550234c647c2459a0dbb FOREIGN KEY(game_id, job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.curated_image_import_batches ADD CONSTRAINT v2_fk_d7c43705058b9bb40859 FOREIGN KEY(game_id, source_id) REFERENCES game_data_v2.curated_image_import_sources (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.curated_image_import_batches ADD CONSTRAINT v2_owner_354406efbd8ff5918050 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.curated_image_import_sources ADD CONSTRAINT v2_fk_471f2e0a32c248cd4a18 FOREIGN KEY(game_id, image_selection_run_id) REFERENCES game_data_v2.image_selection_runs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.curated_image_import_sources ADD CONSTRAINT v2_fk_b6857af431a1933a9d84 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.dataset_versions ADD CONSTRAINT v2_fk_8cdc016d78b665b0a87c FOREIGN KEY(game_id, source_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.dataset_versions ADD CONSTRAINT v2_fk_f092cdad371ec337daf5 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.game_grid_profile_activations ADD CONSTRAINT v2_fk_0c9fa0940a2317a39c7c FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.game_grid_profile_activations ADD CONSTRAINT v2_fk_125316b01f4da3cea7ff FOREIGN KEY(game_id, previous_profile_id) REFERENCES game_data_v2.grid_calibration_profiles (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.game_grid_profile_activations ADD CONSTRAINT v2_fk_fcde7e590ff8c10c53c9 FOREIGN KEY(game_id, profile_id) REFERENCES game_data_v2.grid_calibration_profiles (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.game_symbol_model_activations ADD CONSTRAINT v2_fk_7826c2c8ff99937f6e98 FOREIGN KEY(game_id, model_iteration_id) REFERENCES game_data_v2.symbol_model_iterations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.game_symbol_model_activations ADD CONSTRAINT v2_fk_840fe3f958ccc168613c FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.game_symbol_model_activations ADD CONSTRAINT v2_fk_f37ddd41c92cd62ddb1c FOREIGN KEY(game_id, previous_model_iteration_id) REFERENCES game_data_v2.symbol_model_iterations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.grid_calibration_profiles ADD CONSTRAINT v2_fk_56930a63fb4df52e02da FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.grid_calibration_profiles ADD CONSTRAINT v2_fk_b2ba0fb1fd0640752009 FOREIGN KEY(game_id, cohort_id) REFERENCES game_data_v2.grid_geometry_cohorts (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.grid_geometry_cohorts ADD CONSTRAINT v2_fk_4cae779509d44d127dac FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_pending ADD CONSTRAINT v2_fk_43bd0f44112e1406b098 FOREIGN KEY(game_id, source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_pending ADD CONSTRAINT v2_fk_49e0e1b4a1675bdca9bc FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_pending ADD CONSTRAINT v2_fk_9271ed4a32559e3ca384 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_pending ADD CONSTRAINT v2_fk_e2b2e245b6bb54805757 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_pending ADD CONSTRAINT v2_fk_f15ef7d9b335f94d8f42 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_review_events ADD CONSTRAINT v2_fk_364433199cb7271b5112 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_review_events ADD CONSTRAINT v2_fk_e0ba53f5b3462d8697aa FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_review_events ADD CONSTRAINT v2_owner_925e1cf0ce7b149f7d47 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_revisions ADD CONSTRAINT v2_fk_2d9b3a358b2f83cb0db7 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_revisions ADD CONSTRAINT v2_fk_745aef4c7467937e84d6 FOREIGN KEY(game_id, source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_revisions ADD CONSTRAINT v2_fk_fc2f3f863514d11e7971 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_geometry_revisions ADD CONSTRAINT v2_owner_08f7541752ca6b7a8834 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_search_candidates ADD CONSTRAINT v2_fk_1dac2d1a94450d538ada FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_search_candidates ADD CONSTRAINT v2_fk_397847c7bd2234944985 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_board_search_candidates ADD CONSTRAINT v2_fk_982a176a5576258f40e3 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_search_candidates ADD CONSTRAINT v2_fk_b219e8d5f3e0b03ea121 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_search_fast_documents ADD CONSTRAINT v2_fk_a4e43b06e452fbc9aa60 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_board_search_candidates (game_id, review_item_id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_board_search_fast_documents ADD CONSTRAINT v2_fk_e93169ad735df74053d7 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_board_search_projection_states ADD CONSTRAINT v2_fk_3896f9a3f0cdb5aaec75 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_geometry_rollout_states ADD CONSTRAINT v2_fk_2a1a14ed4c0683f7f970 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_geometry_rollout_states ADD CONSTRAINT v2_fk_89a9dd07436a0a94e8e8 FOREIGN KEY(game_id, validation_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_geometry_rollout_states ADD CONSTRAINT v2_fk_e078a76ed5992834a358 FOREIGN KEY(game_id, last_source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_geometry_guard_decisions ADD CONSTRAINT v2_fk_2d906b315050c502f895 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_geometry_guard_decisions ADD CONSTRAINT v2_fk_35ef41a273ab4f31ba83 FOREIGN KEY(game_id, browser_selection_id) REFERENCES game_data_v2.browser_selection_retention_states (game_id, upload_id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_geometry_guard_decisions ADD CONSTRAINT v2_fk_cf06e7908e9c6221988c FOREIGN KEY(game_id, guard_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_geometry_guard_resolution_manifests ADD CONSTRAINT v2_fk_1e36c2753e05de31e34b FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_geometry_guard_resolution_manifests ADD CONSTRAINT v2_fk_23f12b428eb9e9f74a70 FOREIGN KEY(game_id, guard_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_geometry_guard_resolution_manifests ADD CONSTRAINT v2_fk_63df5ae968e77143cb9c FOREIGN KEY(game_id, browser_selection_id) REFERENCES game_data_v2.browser_selection_retention_states (game_id, upload_id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_job_files ADD CONSTRAINT v2_fk_14a0c9ae5a5412afa745 FOREIGN KEY(file_execution_key) REFERENCES public.image_file_executions (file_execution_key) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_job_files ADD CONSTRAINT v2_fk_4d743cfe563650cf36c7 FOREIGN KEY(game_id, job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_import_job_files ADD CONSTRAINT v2_owner_a920f6b4053203b36ffe FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_layout_staging_rows ADD CONSTRAINT v2_fk_16feb976eabdfc8972ce FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_layout_staging_rows ADD CONSTRAINT v2_fk_6f9c15c9a75aa6e86e53 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_layout_staging_rows ADD CONSTRAINT v2_fk_a3512093422497db7bb1 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_layout_staging_rows ADD CONSTRAINT v2_owner_4e285c384562d25380d9 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_page_geometry_overrides ADD CONSTRAINT v2_fk_ff24c7b25e8faa4f1ee4 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_page_source_exclusions ADD CONSTRAINT v2_fk_ae889dd4103401f36e7a FOREIGN KEY(game_id, browser_selection_id) REFERENCES game_data_v2.browser_selection_retention_states (game_id, upload_id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_page_source_exclusions ADD CONSTRAINT v2_fk_e7f00fe1c532dc05dbc4 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_items ADD CONSTRAINT v2_fk_018543dfbe47ce8c3626 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_items ADD CONSTRAINT v2_fk_bf21a5c695ae4f7aa049 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_items ADD CONSTRAINT v2_fk_ee8970537f6ebb37be73 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_queue_items ADD CONSTRAINT v2_fk_56924abfb3cc0499143a FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_review_queue_items ADD CONSTRAINT v2_fk_bfe0a764f651cc2315ac FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_review_queue_items ADD CONSTRAINT v2_owner_5190a34a41ee956518d5 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_queue_states ADD CONSTRAINT v2_fk_53952384789f2c5ea581 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_review_queue_states ADD CONSTRAINT v2_owner_d8c64ac9090188fe8ab0 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_resolution_events ADD CONSTRAINT v2_fk_348731797fa3265dd3b8 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_review_resolution_events ADD CONSTRAINT v2_owner_e325ecabd2402988ad6d FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_candidates ADD CONSTRAINT v2_fk_19b03727ca4ad627acd8 FOREIGN KEY(game_id, run_id, group_id) REFERENCES game_data_v2.image_selection_groups (game_id, run_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_selection_candidates ADD CONSTRAINT v2_fk_cf752b95f284f552df78 FOREIGN KEY(game_id, run_id) REFERENCES game_data_v2.image_selection_runs (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_selection_candidates ADD CONSTRAINT v2_owner_d5388d517a0278a6ec0d FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_groups ADD CONSTRAINT v2_fk_326760382d4ef6fff7b1 FOREIGN KEY(game_id, run_id) REFERENCES game_data_v2.image_selection_runs (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_selection_groups ADD CONSTRAINT v2_fk_93a5e08f8bd887d0fc21 FOREIGN KEY(game_id, origin_group_id) REFERENCES game_data_v2.image_selection_groups (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_groups ADD CONSTRAINT v2_owner_36e9adbddeabe8403a02 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_manual_decisions ADD CONSTRAINT v2_fk_0daf160f21adc5906082 FOREIGN KEY(game_id, run_id, group_id) REFERENCES game_data_v2.image_selection_groups (game_id, run_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_selection_manual_decisions ADD CONSTRAINT v2_fk_5871e2f489e46ae88807 FOREIGN KEY(game_id, candidate_id) REFERENCES game_data_v2.image_selection_candidates (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_manual_decisions ADD CONSTRAINT v2_fk_9f5281e72593d0b19402 FOREIGN KEY(game_id, run_id) REFERENCES game_data_v2.image_selection_runs (game_id, id) ON DELETE CASCADE;

ALTER TABLE game_data_v2.image_selection_manual_decisions ADD CONSTRAINT v2_owner_a5da48d80e5aa73be7ac FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_runs ADD CONSTRAINT v2_fk_02628d4eef2d6ad3398a FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_runs ADD CONSTRAINT v2_fk_1507b4c802feb27e9a06 FOREIGN KEY(game_id, job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_selection_runs ADD CONSTRAINT v2_fk_a274e44b516d71d5790c FOREIGN KEY(game_id, source_run_id) REFERENCES game_data_v2.image_selection_runs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_alternatives ADD CONSTRAINT v2_fk_4a9afe118674f97b29bb FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_alternatives ADD CONSTRAINT v2_fk_4bc94236a8cd0244b83d FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_canonical ADD CONSTRAINT v2_fk_30a4c2875e48dc911776 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_canonical ADD CONSTRAINT v2_fk_4968eb6802d044661959 FOREIGN KEY(game_id, source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_canonical ADD CONSTRAINT v2_fk_4ce66cce1df7a3020090 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_canonical ADD CONSTRAINT v2_fk_53ec306b94375df5bf42 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_canonical ADD CONSTRAINT v2_fk_70154b79d00a81b0b0ff FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_source_override_events ADD CONSTRAINT v2_fk_857675ba219cb341058f FOREIGN KEY(game_id, selected_review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_sequence_source_override_events ADD CONSTRAINT v2_fk_b9ab2d24d7c2a3f6279a FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_source_geometry_revisions ADD CONSTRAINT v2_fk_0cd8a24555f45901370a FOREIGN KEY(game_id, topology_rules_version_id) REFERENCES public.rules_versions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_source_geometry_revisions ADD CONSTRAINT v2_fk_81bb5c389f3c24fe51bf FOREIGN KEY(game_id, source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_source_geometry_revisions ADD CONSTRAINT v2_fk_820f8b2b2bfa27e63b71 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_prediction_revisions ADD CONSTRAINT v2_fk_a39a59b243d1928ea1c6 FOREIGN KEY(game_id, source_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_prediction_revisions ADD CONSTRAINT v2_fk_a7758792b2db8d98b414 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_prediction_revisions ADD CONSTRAINT v2_fk_cedac91148c948dfa3dd FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_prediction_revisions ADD CONSTRAINT v2_fk_f4f81cb2eb82f22c43e0 FOREIGN KEY(game_id, model_iteration_id) REFERENCES game_data_v2.symbol_model_iterations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_prediction_revisions ADD CONSTRAINT v2_fk_f7937020763b6cd6ad02 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_operations ADD CONSTRAINT v2_fk_1a1ea3b18692e939e91d FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_operations ADD CONSTRAINT v2_fk_5f0db50668f52af2bc70 FOREIGN KEY(game_id, filter_symbol_id) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_operations ADD CONSTRAINT v2_fk_c6d7c917648ed7fe1402 FOREIGN KEY(game_id, job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_operations ADD CONSTRAINT v2_fk_dbcfae6218fac353b73f FOREIGN KEY(game_id, target_symbol_id) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_targets ADD CONSTRAINT v2_fk_198c22c290bb008bd1e7 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_targets ADD CONSTRAINT v2_fk_4b798377b2de6246546c FOREIGN KEY(game_id, cell_review_id) REFERENCES game_data_v2.image_symbol_review_cells (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_targets ADD CONSTRAINT v2_fk_a716ebc1aaaecc332f72 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_targets ADD CONSTRAINT v2_fk_c8333010cf40723255aa FOREIGN KEY(game_id, operation_id) REFERENCES game_data_v2.image_symbol_review_bulk_operations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_bulk_targets ADD CONSTRAINT v2_owner_bb2389349d70a3d8c6be FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_0e5970aa21879e7384bd FOREIGN KEY(game_id, approved_source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_7913fda68b24dca91690 FOREIGN KEY(game_id, source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_84659059f8c09f577281 FOREIGN KEY(game_id, verified_symbol_id_v2) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_8d85362d62b5f696b081 FOREIGN KEY(game_id, assigned_symbol_id) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_8dcccaae262a7dea7047 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_8fa558a43895130f256e FOREIGN KEY(game_id, prediction_revision_id) REFERENCES game_data_v2.image_symbol_prediction_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_9745dc600a9897bd6226 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_b15df8e35ee3ebb8467b FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_cells ADD CONSTRAINT v2_fk_e98b5d1da7c890232451 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_2619e99a526e5e2058f6 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_27da886793c4b9cb0f74 FOREIGN KEY(game_id, verified_symbol_id_v2) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_2e92779b97a25c916590 FOREIGN KEY(game_id, previous_approved_source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_3ccfc7c82027e35fcc78 FOREIGN KEY(game_id, cell_review_id) REFERENCES game_data_v2.image_symbol_review_cells (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_46a13b8a2664a6c84954 FOREIGN KEY(game_id, previous_verified_symbol_id_v2) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_7be4ef9ee4c02b271d7d FOREIGN KEY(game_id, approved_source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_835975875a27bfe888cd FOREIGN KEY(game_id, source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_a110540a73bd0fa4b8c3 FOREIGN KEY(game_id, assigned_symbol_id) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_aa44eb1c669503500ee7 FOREIGN KEY(game_id, previous_source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_b683f61cd6b3a9bd9394 FOREIGN KEY(game_id, operation_id) REFERENCES game_data_v2.image_symbol_review_bulk_operations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_fk_e976144b0786165954b9 FOREIGN KEY(game_id, previous_assigned_symbol_id) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_events ADD CONSTRAINT v2_owner_b10958d3d1b3e46ca476 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_symbol_review_states ADD CONSTRAINT v2_fk_4c076c4a047e9b18bced FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_verified_cohort_exports ADD CONSTRAINT v2_fk_70ad5030f35bee637aef FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.image_verified_cohort_exports ADD CONSTRAINT v2_fk_b0ebcc1cee29381972d1 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_import_normalized_rows ADD CONSTRAINT v2_fk_0c50e0ddfc7d9984dd8a FOREIGN KEY(game_id, rules_version_id) REFERENCES public.rules_versions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_import_normalized_rows ADD CONSTRAINT v2_fk_929edce408e008d6b9b8 FOREIGN KEY(game_id, validation_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_import_normalized_rows ADD CONSTRAINT v2_fk_c95c40d1ea039046a65b FOREIGN KEY(game_id, import_job_id, line_number) REFERENCES game_data_v2.layout_import_rows (game_id, job_id, line_number) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_import_normalized_rows ADD CONSTRAINT v2_owner_50c92a2a58b01f728464 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_import_rows ADD CONSTRAINT v2_fk_dc0842121b51674b90b4 FOREIGN KEY(game_id, job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_import_rows ADD CONSTRAINT v2_owner_a5e48b1da552ceb053ce FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_payouts ADD CONSTRAINT v2_fk_4f3339c375e04b6644d3 FOREIGN KEY(game_id, dataset_version_id, sequence_number) REFERENCES game_data_v2.layouts (game_id, dataset_version_id, sequence_number) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_payouts ADD CONSTRAINT v2_fk_8aa040e253a34c75f3b8 FOREIGN KEY(game_id, rules_version_id) REFERENCES public.rules_versions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layout_payouts ADD CONSTRAINT v2_owner_a5d0866eeedde3b5b531 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layouts ADD CONSTRAINT v2_fk_1194501f3f4add8f02b5 FOREIGN KEY(game_id, dataset_version_id) REFERENCES game_data_v2.dataset_versions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.layouts ADD CONSTRAINT v2_owner_7c31f497d1da5b02bb27 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.legacy_board_search_archive_documents ADD CONSTRAINT v2_fk_6e59f056870c4bc0aeee FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.legacy_board_search_archive_states ADD CONSTRAINT v2_fk_7b05b27370ba0b53cc0f FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.mobile_release_games ADD CONSTRAINT v2_fk_31a93b20626acd512af1 FOREIGN KEY(mobile_release_id) REFERENCES public.mobile_releases (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.mobile_release_games ADD CONSTRAINT v2_fk_905a8dd4246bce5100cf FOREIGN KEY(game_id, dataset_version_id) REFERENCES game_data_v2.dataset_versions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.mobile_release_games ADD CONSTRAINT v2_fk_dfd8dd2a683edd7f6527 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.mobile_release_games ADD CONSTRAINT v2_fk_fad81eef3492214474b1 FOREIGN KEY(game_id, rules_version_id) REFERENCES public.rules_versions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.recognized_boards ADD CONSTRAINT v2_fk_9199f9ba9457342673ad FOREIGN KEY(game_id, source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.recognized_boards ADD CONSTRAINT v2_fk_a4123004f6e718770de0 FOREIGN KEY(game_id, source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.recognized_boards ADD CONSTRAINT v2_owner_e6550bb4cfba7d4ac0d9 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.representative_ranking_activations ADD CONSTRAINT v2_fk_446cd2f534402d776559 FOREIGN KEY(game_id, iteration_id) REFERENCES game_data_v2.representative_ranking_iterations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.representative_ranking_activations ADD CONSTRAINT v2_fk_fb596f610be88f4e5121 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.representative_ranking_activations ADD CONSTRAINT v2_fk_fd724de640a2f002e3aa FOREIGN KEY(game_id, previous_iteration_id) REFERENCES game_data_v2.representative_ranking_iterations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.representative_ranking_cohorts ADD CONSTRAINT v2_fk_f9987f2b1ed96391f33f FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.representative_ranking_iterations ADD CONSTRAINT v2_fk_2fec48bf1b5a5f1c24ee FOREIGN KEY(game_id, cohort_id) REFERENCES game_data_v2.representative_ranking_cohorts (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.representative_ranking_iterations ADD CONSTRAINT v2_owner_b77c59fdb2875087e538 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_batches ADD CONSTRAINT v2_fk_eed7d541318fcac93835 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_feedback_exports ADD CONSTRAINT v2_fk_7911ea0ea7cb0f84048b FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_feedback_exports ADD CONSTRAINT v2_fk_af8ff20e42ae9a38d221 FOREIGN KEY(game_id, review_batch_id) REFERENCES game_data_v2.review_batches (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_items ADD CONSTRAINT v2_fk_1dfe1b2038dde5db0c01 FOREIGN KEY(game_id, review_batch_id) REFERENCES game_data_v2.review_batches (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_items ADD CONSTRAINT v2_owner_bfd75806b4cf2e37fc9c FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_resolutions ADD CONSTRAINT v2_fk_4e11caf4b120ea46b5fc FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.review_resolutions ADD CONSTRAINT v2_owner_2632fd3c5a203ea23785 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_access_audit_events ADD CONSTRAINT v2_fk_510188a794702536c358 FOREIGN KEY(game_id, session_id) REFERENCES game_data_v2.reviewer_access_sessions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_access_audit_events ADD CONSTRAINT v2_owner_08fdc434437f75349054 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_access_sessions ADD CONSTRAINT v2_fk_66015ea970057adba2c5 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_access_sessions ADD CONSTRAINT v2_fk_e14c0a22b2ab91fbd546 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_work_assignments ADD CONSTRAINT v2_fk_04ca9bb47a7a1086a942 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_work_assignments ADD CONSTRAINT v2_fk_390ac14771a653473bc6 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.reviewer_work_assignments ADD CONSTRAINT v2_fk_5b9f37158aaeafb6639c FOREIGN KEY(game_id, reviewer_access_session_id, import_job_id) REFERENCES game_data_v2.reviewer_access_sessions (game_id, id, import_job_id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.source_images ADD CONSTRAINT v2_fk_90fdac1fbbd0c39bb681 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.source_images ADD CONSTRAINT v2_fk_cf6ada333f55f3a8bcde FOREIGN KEY(file_execution_key) REFERENCES public.image_file_executions (file_execution_key) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.source_images ADD CONSTRAINT v2_owner_437a7eeb64c3a2d1124f FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_model_iterations ADD CONSTRAINT v2_fk_0361090277892a5c8f25 FOREIGN KEY(game_id, cohort_id) REFERENCES game_data_v2.verified_training_cohorts (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_model_iterations ADD CONSTRAINT v2_fk_24d62a38fcef3b0aeefd FOREIGN KEY(game_id, job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_model_iterations ADD CONSTRAINT v2_fk_4dc1499544ab8fb73894 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_reference_images ADD CONSTRAINT v2_fk_657ff3d6c526545fcfa6 FOREIGN KEY(game_id, source_observation_id) REFERENCES game_data_v2.cell_observations (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_reference_images ADD CONSTRAINT v2_fk_76dfa9fecb7b6403afcc FOREIGN KEY(game_id, source_review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_reference_images ADD CONSTRAINT v2_fk_7746675b9b0fccf88d11 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_reference_images ADD CONSTRAINT v2_fk_b56c4fe7c61158a79eca FOREIGN KEY(game_id, source_recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.symbol_reference_images ADD CONSTRAINT v2_fk_e6c8d462f3fbcc4389d4 FOREIGN KEY(game_id, symbol_id) REFERENCES public.symbols (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_fk_24c55f0b72c652d543ba FOREIGN KEY(game_id, cell_review_id) REFERENCES game_data_v2.image_symbol_review_cells (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_fk_2c7a1d975fd782c65aff FOREIGN KEY(game_id, source_geometry_revision_id) REFERENCES game_data_v2.image_source_geometry_revisions (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_fk_4d8e08f81ab865d4152c FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_fk_80b1d38f31fa0df5dca9 FOREIGN KEY(game_id, source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_fk_c3c20039cbf032bad935 FOREIGN KEY(game_id, cohort_id) REFERENCES game_data_v2.verified_training_cohorts (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_fk_de3de36a82b656d85001 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_cells ADD CONSTRAINT v2_owner_9c1e4035ac0014931895 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_items ADD CONSTRAINT v2_fk_724b66189ea3cfafb8bb FOREIGN KEY(game_id, source_image_id) REFERENCES game_data_v2.source_images (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_items ADD CONSTRAINT v2_fk_73783c41d4f6f5457cc3 FOREIGN KEY(game_id, import_job_id) REFERENCES public.jobs (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_items ADD CONSTRAINT v2_fk_83c8ce867c7d965e3ed6 FOREIGN KEY(game_id, review_item_id) REFERENCES game_data_v2.image_review_items (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_items ADD CONSTRAINT v2_fk_9a094658ddbb58970464 FOREIGN KEY(game_id, cohort_id) REFERENCES game_data_v2.verified_training_cohorts (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_items ADD CONSTRAINT v2_fk_fe572123b42ae4abd712 FOREIGN KEY(game_id, recognized_board_id) REFERENCES game_data_v2.recognized_boards (game_id, id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohort_items ADD CONSTRAINT v2_owner_1340ae3d61b51b3b4b35 FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;

ALTER TABLE game_data_v2.verified_training_cohorts ADD CONSTRAINT v2_fk_e1374a322744746cc45f FOREIGN KEY(game_id) REFERENCES public.games (id) ON DELETE RESTRICT;
