"""Shared PostgreSQL shape constraint for migration and ORM source bindings."""


def _range_integer(range_name: str, key: str) -> str:
    value = f"neural_proposal_binding->'{range_name}'->'{key}'"
    text = f"neural_proposal_binding->'{range_name}'->>'{key}'"
    return f"jsonb_typeof({value}) = 'number' AND {text} ~ '^[1-9][0-9]{{0,8}}$'"


def _range_value(range_name: str, key: str) -> str:
    return f"(neural_proposal_binding->'{range_name}'->>'{key}')::integer"


_RANGE_FIELDS = [
    _range_integer(name, key)
    for name in ("originalRange", "confirmedRange")
    for key in ("sequenceRangeStart", "sequenceRangeEnd")
]
_ORIGINAL_START = _range_value("originalRange", "sequenceRangeStart")
_ORIGINAL_END = _range_value("originalRange", "sequenceRangeEnd")
_CONFIRMED_START = _range_value("confirmedRange", "sequenceRangeStart")
_CONFIRMED_END = _range_value("confirmedRange", "sequenceRangeEnd")

NEURAL_PAGE_BINDING_CHECK = f"""
neural_proposal_binding IS NULL OR ((
    jsonb_typeof(neural_proposal_binding) = 'object' AND
    neural_proposal_binding ?& ARRAY['contractVersion','gameId','sourceSelectionId',
        'sourceChecksumSha256','sourceWidth','sourceHeight','proposalChecksumSha256',
        'originalRange','confirmedRange','assignments','missingPositionIndexes',
        'ignoredDetectionIds'] AND
    neural_proposal_binding->>'contractVersion' = 'neural-source-binding-v1' AND
    neural_proposal_binding->>'gameId' = game_id::text AND
    neural_proposal_binding->>'sourceSelectionId'
        ~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$' AND
    jsonb_typeof(neural_proposal_binding->'sourceChecksumSha256') = 'string' AND
    neural_proposal_binding->>'sourceChecksumSha256' = source_checksum_sha256 AND
    CASE WHEN
        jsonb_typeof(neural_proposal_binding->'sourceWidth') = 'number' AND
        jsonb_typeof(neural_proposal_binding->'sourceHeight') = 'number' AND
        neural_proposal_binding->>'sourceWidth' ~ '^[1-9][0-9]{{0,8}}$' AND
        neural_proposal_binding->>'sourceHeight' ~ '^[1-9][0-9]{{0,8}}$'
    THEN (neural_proposal_binding->>'sourceWidth')::integer = image_width
         AND (neural_proposal_binding->>'sourceHeight')::integer = image_height
    ELSE false END AND
    jsonb_typeof(neural_proposal_binding->'proposalChecksumSha256') = 'string' AND
    neural_proposal_binding->>'proposalChecksumSha256' ~ '^[0-9a-f]{{64}}$' AND
    jsonb_typeof(neural_proposal_binding->'originalRange') = 'object' AND
    jsonb_typeof(neural_proposal_binding->'confirmedRange') = 'object' AND
    CASE WHEN {" AND ".join(_RANGE_FIELDS)}
    THEN {_ORIGINAL_END} BETWEEN {_ORIGINAL_START} AND {_ORIGINAL_START} + 8
         AND {_CONFIRMED_START} >= {_ORIGINAL_START}
         AND {_CONFIRMED_END} <= {_ORIGINAL_END}
         AND {_CONFIRMED_END} BETWEEN {_CONFIRMED_START} AND {_CONFIRMED_START} + 8
    ELSE false END AND
    CASE WHEN
        jsonb_typeof(neural_proposal_binding->'assignments') = 'array' AND
        jsonb_typeof(neural_proposal_binding->'missingPositionIndexes') = 'array' AND
        jsonb_typeof(neural_proposal_binding->'ignoredDetectionIds') = 'array'
    THEN
        jsonb_array_length(neural_proposal_binding->'assignments') <= 9 AND
        jsonb_array_length(neural_proposal_binding->'missingPositionIndexes') <= 9 AND
        jsonb_array_length(neural_proposal_binding->'ignoredDetectionIds') <= 256 AND
        neural_proposal_binding->'assignments' = jsonb_path_query_array(
            neural_proposal_binding, '$.assignments[*] ? (
                @.type() == "object" && @.detectionId.type() == "string" &&
                @.detectionId like_regex "[^[:space:]]" &&
                @.positionIndex.type() == "number" &&
                @.positionIndex >= 0 && @.positionIndex <= 8 &&
                @.positionIndex.floor() == @.positionIndex)') AND
        neural_proposal_binding->'missingPositionIndexes' = jsonb_path_query_array(
            neural_proposal_binding, '$.missingPositionIndexes[*] ? (
                @.type() == "number" && @ >= 0 && @ <= 8 && @.floor() == @)') AND
        neural_proposal_binding->'ignoredDetectionIds' = jsonb_path_query_array(
            neural_proposal_binding, '$.ignoredDetectionIds[*] ? (
                @.type() == "string" && @ like_regex "[^[:space:]]")')
    ELSE false END AND
    slot_qualifications IS NULL AND board_frame_quads IS NULL AND symbol_grid_quads IS NULL
) IS TRUE)
"""
