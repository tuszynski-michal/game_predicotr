select im.id::text as source_id, im.import_job_id::text as import_id, im.file_execution_key, im.relative_path, im.checksum_sha256, curr.sequence_range_start, curr.sequence_range_end, curr.topology_rules_version_id::text, b.sequence_number, b.position_index, im.normalized_pixel_checksum_sha256 as photo,
 b.completeness_status, r.revision,r.id::text as manual_revision_id,r.created_at,
 (case when r.revision=1 and i.snapshot->>'sourceChecksumSha256'=im.checksum_sha256 and i.snapshot->>'geometryChecksumSha256'=parent.geometry_checksum_sha256 then i.snapshot->'geometry' when prev.id is not null then prev.geometry end)->'latticeNodes' as orig,
 r.geometry->'latticeNodes' as edited,
 m.role, m.frozen->'used' as used, m.frozen->'reasons' as reasons, pos.item as cohort_position, parent.geometry_source as prior_kind, e.nc, e.np,
 (r.geometry=sameboard.board_geometry) as eq,
 (select jsonb_agg(jsonb_build_array(slot->>'positionIndex',slot->'latticeNodes')) from jsonb_array_elements(parent.board_geometries) slot) as neighbors
from image_board_geometry_revisions r
join recognized_boards b on b.id=r.recognized_board_id and b.game_id=r.game_id
join recognized_boards sameboard on sameboard.id=b.id
join image_review_items i on i.id=r.review_item_id and i.game_id=r.game_id
join source_images im on im.id=b.source_image_id and im.game_id=r.game_id
join image_source_geometry_revisions curr on curr.id=r.source_geometry_revision_id and curr.game_id=r.game_id and curr.source_image_id=im.id
left join lateral (select count(distinct cell_review_id) nc, count(distinct previous_source_geometry_revision_id) np, min(previous_source_geometry_revision_id::text)::uuid parentid from image_symbol_review_events e where e.game_id=r.game_id and e.review_item_id=r.review_item_id and e.action='geometry_invalidated' and e.source_geometry_revision_id=r.source_geometry_revision_id and e.geometry_revision=r.revision) e on true
left join image_source_geometry_revisions parent on parent.id=e.parentid and parent.game_id=r.game_id and parent.source_image_id=im.id and parent.source_checksum_sha256=im.checksum_sha256 and parent.normalized_pixel_checksum_sha256=im.normalized_pixel_checksum_sha256
left join image_board_geometry_revisions prev on prev.game_id=r.game_id and prev.recognized_board_id=b.id and prev.review_item_id=i.id and prev.revision=r.revision-1 and prev.source_geometry_revision_id=parent.id
left join grid_training_cohort_members m on m.game_id=r.game_id and m.source_id=im.id and m.cohort_id=:cohort
left join lateral (select jsonb_build_object('reason',value->'reason','label',
 case when value->'label'->'nodes' is not null then jsonb_build_object(
 'nodes',value->'label'->'nodes','approval',value->'label'->'approval') end) item
 from jsonb_array_elements(m.frozen->'positions') where (value->>'positionIndex')::int=b.position_index) pos on true
where r.game_id=:g and r.corrected_by in ('local-admin','reviewer-operator') and curr.geometry_source='manual' and curr.status <> 'reverted'
and b.geometry_revision=r.revision and b.approved_geometry_revision=r.revision
and curr.source_checksum_sha256=im.checksum_sha256 and curr.normalized_pixel_checksum_sha256=im.normalized_pixel_checksum_sha256
and (not :exact_train or (
  m.role='TRAIN' and m.frozen->'used'='true'::jsonb
  and pos.item#>'{label,nodes}'=r.geometry->'latticeNodes'
  and pos.item#>>'{label,approval,geometryRevision}'=r.revision::text
  and pos.item#>>'{label,approval,manualRevisionId}'=r.id::text
))
order by b.sequence_number, b.id
