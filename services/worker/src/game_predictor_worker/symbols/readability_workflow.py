"""General-lane independent quality jobs; one source and <=128 crops per extraction."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.domain.symbol_readability import (
    CHECKPOINT_PATH,
    CHECKPOINT_SHA,
    DATASET_PATH,
    DATASET_SHA,
    ReadabilityWorkflowError,
    crop_identity,
    identity_is_current,
)
from game_predictor_api.storage.cell_render_specs import (
    CellRenderSpecError,
    CellRenderSpecKey,
    load_cell_render_specs,
)
from game_predictor_api.storage.source_recording_groups import SqlAlchemySourceRecordingRepository
from game_predictor_api.storage.symbol_readability import (
    SNAPSHOT_SQL,
    SqlAlchemyReadabilityRepository,
)
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.filesystem import long_path_aware
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    CanonicalSourceLoadError,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VirtualCellExtractionError,
    render_persisted_virtual_cell_rgb,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError
from game_predictor_worker.symbols.readability_cohort import QualitySample, Split, assign_families
from game_predictor_worker.symbols.readability_confidence import (
    PROVENANCE,
    load_pinned_calibration,
    pinned_top1,
)
from game_predictor_worker.symbols.readability_detector import (
    evaluate_pilot,
    load_artifact,
    train_detector,
)
from game_predictor_worker.symbols.readability_features import (
    PREPROCESSING,
    FrozenBase,
    ReadabilityError,
    extract_features,
    fingerprint,
    managed_path,
    preflight_base,
)
from game_predictor_worker.symbols.readability_inventory import (
    candidate_snapshots,
    has_replacement_fences,
)
from game_predictor_worker.symbols.readability_selection import (
    base_aliases,
    freeze_pilot_selection,
    source_keys,
)


def sample_from_item(item: Mapping[str, Any]) -> QualitySample:
    row = item["snapshot"]
    return QualitySample(
        cell_id=str(item["cell_id"]),
        sequence_number=item["sequence_number"],
        source_id=str(item["source_id"]),
        source_sha256=row["source_sha256"],
        rgb_sha256=row["rendered_pixel_checksum_sha256"],
        geometry_identity=item["identity"],
        import_id=row["import_job_id"],
        symbol_class=row["symbol_class"],
        historical_unreadable=item["historical_unreadable"],
        overlap=item["overlap"],
        unreadable=True
        if item["state"] == "unreadable"
        else False
        if item["state"] == "readable"
        else None,
        recording_id=row.get("recording_id"),
        sharp=item["sharp"],
        similar_readable=item["similar_readable"],
        top1=row.get("quality_top1") if row.get("confidence_provenance") == PROVENANCE else None,
        previously_unlabelled=item["sample_kind"] == "audit",
    )


def extract_source_features(model: Any, crops: Sequence[Any]) -> np.ndarray[Any, Any]:
    """A 135-cell source is one checkpoint, but two bounded model calls."""
    return np.concatenate(
        [extract_features(model, crops[start : start + 128]) for start in range(0, len(crops), 128)]
    )


def managed_source_path(root: Path, checksum: str) -> Path:
    return managed_path(root, f"data/originals/{checksum[:2]}/{checksum}.jpg")


def publish_quality_artifact(
    root: Path, game: UUID, model: UUID, document: Mapping[str, Any]
) -> str:
    """An expired writer can publish another content address, never replace the accepted one."""
    checksum = document["fingerprint"]
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(c not in "0123456789abcdef" for c in checksum)
    ):
        raise ReadabilityError("READABILITY_ARTIFACT_INVALID", "Artifact fingerprint is invalid.")
    relative = f"data/readability/{game}/{model}/{checksum}.json"
    destination = long_path_aware(managed_path(root, relative))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".tmp-{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(document, allow_nan=False), encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return relative


class ReadabilityHandler:
    def __init__(self, session_factory: sessionmaker[Session], artifact_root: Path) -> None:
        self.factory = session_factory
        self.root = artifact_root

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.job_type is not JobType.SYMBOL_READABILITY or job.game_id is None:
            raise JobHandlerError("READABILITY_JOB_INVALID", "Invalid quality job.")
        try:
            identifier = UUID(str(job.input_payload["identifier"]))
            action = job.input_payload["action"]
            base, model = preflight_base(
                managed_path(self.root, CHECKPOINT_PATH),
                managed_path(self.root, DATASET_PATH),
                self.root / "data",
                checkpoint_sha256=CHECKPOINT_SHA,
                dataset_sha256=DATASET_SHA,
                preprocessing=PREPROCESSING,
            )
            if action == "fit":
                self.fit(context, job, identifier, base)
            elif action in {"prepare", "scan"}:
                self.inventory(job, identifier, base, context=context)
                self.process(context, job, identifier, base, model)
            else:
                raise ReadabilityWorkflowError("READABILITY_JOB_INVALID", "Unknown quality action.")
        except (ReadabilityWorkflowError, ReadabilityError) as error:
            raise JobHandlerError(error.code, str(error)) from error

    def _repo(self, session: Session, job: Job) -> SqlAlchemyReadabilityRepository:
        assert job.game_id is not None
        repo = SqlAlchemyReadabilityRepository(session)
        repo.bind(job.game_id, write=True)
        return repo

    def _recording(self, session: Session, game: UUID, source: str) -> str | None:
        page = SqlAlchemySourceRecordingRepository(session).list_groups(
            game, None, 100, None, source_id=UUID(source)
        )
        ids = sorted({str(row["id"]) for row in page["items"]})
        if len(ids) > 1 or page.get("nextCursor"):
            raise ReadabilityError(
                "READABILITY_PROVENANCE_INVALID",
                "Overlapping recording memberships require explicit family resolution.",
            )
        return ids[0] if ids else None

    def fence(self, session: Session, job: Job) -> None:
        valid = session.scalar(
            text(
                "SELECT id FROM public.jobs WHERE id=:id AND game_id=:game AND "
                "status='processing' AND lease_token=:token AND "
                "lease_expires_at>now() FOR UPDATE"
            ),
            {"id": job.id, "game": job.game_id, "token": job.lease_token},
        )
        if valid is None:
            raise ReadabilityError(
                "READABILITY_LEASE_LOST", "Quality job no longer owns the execution lease."
            )

    def scan_inventory(
        self, job: Job, identifier: UUID, context: JobExecutionContext | None
    ) -> None:
        """Freeze bounded source snapshots; the receipt survives every source commit."""
        assert job.game_id is not None
        while True:
            with self.factory() as session, session.begin():
                repo = self._repo(session, job)
                repo.acquire_write_lock(job.game_id)
                run = repo.row("runs", job.game_id, identifier)
                if run["job_id"] != job.id:
                    raise ReadabilityError("READABILITY_JOB_INVALID", "Run/job binding differs.")
                if run["inventory_fingerprint"] is not None:
                    return
                accepted = repo.row("models", job.game_id, run["model_id"])
                pilot = repo.row("runs", job.game_id, accepted["pilot_run_id"])
                repo._require_pilot_current(job.game_id, pilot["id"])
                if (
                    not accepted["accepted"]
                    or accepted["report"].get("status") != "PASS"
                    or accepted["report"].get("fullScanAllowed") is not True
                    or accepted["pilot_revision"] != pilot["revision"]
                ):
                    raise ReadabilityError(
                        "READABILITY_ACCEPTANCE_REQUIRED", "Pilot acceptance is stale."
                    )
                receipt = run["receipt"]
                source = session.scalar(
                    text("""SELECT s.id FROM source_images s WHERE s.game_id=:game
                  AND (CAST(:after AS uuid) IS NULL OR s.id>CAST(:after AS uuid))
                  AND EXISTS(SELECT 1 FROM recognized_boards b JOIN image_symbol_review_cells c
                    ON c.recognized_board_id=b.id AND c.game_id=b.game_id
                    JOIN image_review_items r ON r.id=c.review_item_id AND r.game_id=c.game_id
                    WHERE b.game_id=s.game_id AND b.source_image_id=s.id AND r.status<>'rejected')
                  ORDER BY s.id LIMIT 1"""),
                    {"game": job.game_id, "after": receipt.get("inventoryLastSource")},
                )
                self.fence(session, job)
                if source is None:
                    session.execute(
                        text(
                            "UPDATE symbol_readability_runs SET "
                            "inventory_fingerprint=:sha,status='processing' WHERE "
                            "game_id=:game AND id=:run"
                        ),
                        {
                            "game": job.game_id,
                            "run": identifier,
                            "sha": receipt.get("inventoryDigest", fingerprint([])),
                        },
                    )
                    return
                rows = (
                    session.execute(
                        text(
                            SNAPSHOT_SQL
                            + " AND s.id=:source ORDER BY c.sequence_number,c.cell_index,c.id "
                            "LIMIT 10001"
                        ),
                        {"game": job.game_id, "source": source},
                    )
                    .mappings()
                    .all()
                )
                if len(rows) > 10000:
                    raise ReadabilityError(
                        "READABILITY_SOURCE_LIMIT",
                        "One source exceeds the bounded inventory limit.",
                    )
                snapshots = [dict(row["snapshot"]) for row in rows]
                if snapshots:
                    session.execute(
                        text("""INSERT INTO symbol_readability_items
(game_id,run_id,cell_id,source_id,sequence_number,cell_index,snapshot,identity,
                       sample_kind,historical_unreadable,state)
                      VALUES(:game,:run,:cell,:source,:seq,:index,CAST(:snapshot AS
jsonb),:identity,
                        'scan',:historical,:state) ON CONFLICT DO NOTHING"""),
                        [
                            {
                                "game": job.game_id,
                                "run": identifier,
                                "cell": row["cell_id"],
                                "source": source,
                                "seq": row["sequence_number"],
                                "index": row["cell_index"],
                                "snapshot": json.dumps(row),
                                "identity": crop_identity(row),
                                "historical": row.get("quality_issue") == "unreadable",
                                "state": "unreadable"
                                if row.get("quality_issue") == "unreadable"
                                else "pending",
                            }
                            for row in snapshots
                        ],
                    )
                receipt = {
                    "modelFingerprint": accepted["fingerprint"],
                    "inventoryLastSource": str(source),
                    "inventoryDigest": fingerprint(
                        [
                            receipt.get("inventoryDigest"),
                            str(source),
                            [crop_identity(row) for row in snapshots],
                        ]
                    ),
                }
                count = run["item_count"] + len(snapshots)
                session.execute(
                    text(
                        "UPDATE symbol_readability_runs SET receipt=CAST(:receipt AS "
                        "jsonb),item_count=:count WHERE game_id=:game AND id=:run"
                    ),
                    {
                        "game": job.game_id,
                        "run": identifier,
                        "receipt": json.dumps(receipt),
                        "count": count,
                    },
                )
            if context is not None:
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "run_id": str(identifier),
                        "inventoryLastSource": str(source),
                    },
                    stage="readability_inventory",
                    current=count,
                    total=count,
                    success_count=count,
                    failure_count=0,
                    review_count=0,
                )

    def inventory(
        self,
        job: Job,
        identifier: UUID,
        base: FrozenBase,
        *,
        context: JobExecutionContext | None = None,
    ) -> None:
        assert job.game_id is not None
        with self.factory() as session, session.begin():
            repo = self._repo(session, job)
            kind = repo.row("runs", job.game_id, identifier)["kind"]
        if kind == "scan":
            self.scan_inventory(job, identifier, context)
            return
        with self.factory() as session, session.begin():
            repo = self._repo(session, job)
            repo.acquire_write_lock(job.game_id)
            run = repo.row("runs", job.game_id, identifier)
            if run["job_id"] != job.id:
                raise ReadabilityWorkflowError(
                    "READABILITY_JOB_INVALID", "Run/job binding differs."
                )
            if run["inventory_fingerprint"] is not None:
                return
            base_recordings: dict[str, set[str]] = {}
            recordings: dict[str, str | None] = {}
            last_heartbeat = time.monotonic()

            def progress() -> None:
                nonlocal last_heartbeat
                if context is not None and time.monotonic() - last_heartbeat >= 10:
                    context.heartbeat()
                    last_heartbeat = time.monotonic()

            for source in sorted({row["sourceId"] for row in base.members}):
                progress()
                group = self._recording(session, job.game_id, source)
                if group:
                    base_recordings.setdefault(group, set()).update(
                        row["split"] for row in base.members if row["sourceId"] == source
                    )
            replacement_fences = has_replacement_fences(session, job.game_id)

            game_id = job.game_id

            def eligible_rows() -> Iterator[dict[str, Any]]:
                stream = candidate_snapshots(
                    session,
                    game_id,
                    run["seed"],
                    audit=False,
                    replacement_fences=replacement_fences,
                    progress=progress,
                )
                try:
                    for row in stream:
                        progress()
                        source = row["source_id"]
                        if source not in recordings:
                            recordings[source] = self._recording(session, game_id, source)
                        row["recording_id"] = recordings[source]
                        yield row
                finally:
                    stream.close()

            selected = freeze_pilot_selection(eligible_rows, base, base_recordings)
            reserved_keys = set().union(*(set(row["family_keys"]) for row in selected))
            aliases = base_aliases(base)
            pilot_sources = {row["source_id"] for row in selected}
            pilot_sha = {row["source_sha256"] for row in selected}
            pilot_rgb = {row["rendered_pixel_checksum_sha256"] for row in selected}
            excluded_recordings = {
                row["recording_id"] for row in selected if row.get("recording_id")
            }
            base_exposed = [row for row in base.members if row["split"] in {"train", "validation"}]
            forbidden_sources = {row["sourceId"] for row in base_exposed} | pilot_sources
            forbidden_sha = {row["sourceSha256"] for row in base_exposed} | pilot_sha
            forbidden_rgb = {row["rgbSha256"] for row in base_exposed} | pilot_rgb
            excluded_recordings.update(
                group
                for group, splits in base_recordings.items()
                if splits & {"train", "validation"}
            )
            # The random order is frozen before labels. Filtering defines a limited,
            # independent population; its noise report never describes the whole game.
            audit = []
            stream = candidate_snapshots(
                session,
                game_id,
                run["seed"] + ":audit",
                audit=True,
                replacement_fences=replacement_fences,
                progress=progress,
            )
            try:
                for row in stream:
                    progress()
                    if (
                        row["source_id"] in forbidden_sources
                        or row["source_sha256"] in forbidden_sha
                        or row["rendered_pixel_checksum_sha256"] in forbidden_rgb
                    ):
                        continue
                    source = row["source_id"]
                    if source not in recordings:
                        recordings[source] = self._recording(session, job.game_id, source)
                    row["recording_id"] = recordings[source]
                    keys = source_keys(row)
                    keys |= set().union(*(aliases.get(key, set()) for key in keys))
                    if keys & reserved_keys:
                        continue
                    if row["recording_id"] in excluded_recordings:
                        continue
                    audit.append(row)
                    if len(audit) == 200:
                        break
            finally:
                stream.close()
            if len(audit) != 200:
                raise ReadabilityError(
                    "READABILITY_PILOT_STOP",
                    "Independent previously unlabelled audit200 pool unavailable.",
                )
            for kind, frozen_rows in (("pilot", selected), ("audit", audit)):
                session.execute(
                    text("""INSERT INTO symbol_readability_items
(game_id,run_id,cell_id,source_id,sequence_number,cell_index,snapshot,identity,sample_kind,historical_unreadable)
                  VALUES(:game,:run,:cell,:source,:seq,:index,CAST(:snapshot AS
jsonb),:identity,:kind,:historical)"""),
                    [
                        {
                            "game": job.game_id,
                            "run": identifier,
                            "cell": row["cell_id"],
                            "source": row["source_id"],
                            "seq": row["sequence_number"],
                            "index": row["cell_index"],
                            "snapshot": json.dumps(row),
                            "identity": crop_identity(row),
                            "kind": kind,
                            "historical": row.get("quality_issue") == "unreadable",
                        }
                        for row in frozen_rows
                    ],
                )
            receipt = {
                "selection": "uniform-random-before-labels",
                "seed": run["seed"] + ":audit",
                "population": "previously-unlabelled families outside pilot and base TRAIN/VAL",
                "baseRecordings": {key: sorted(value) for key, value in base_recordings.items()},
                "identitiesSha256": fingerprint(
                    sorted(
                        fingerprint(
                            {
                                "cell": row["cell_id"],
                                "rgb": row["rendered_pixel_checksum_sha256"],
                                "geometry": crop_identity(row),
                                "source": row["source_sha256"],
                            }
                        )
                        for row in audit
                    )
                ),
            }
            identities = session.execute(
                text(
                    "SELECT cell_id,snapshot FROM symbol_readability_items WHERE "
                    "game_id=:game AND run_id=:run ORDER BY cell_id"
                ),
                {"game": job.game_id, "run": identifier},
                execution_options={"stream_results": True, "yield_per": 250},
            )
            inventory = hashlib.sha256()
            count = 0
            for cell, snapshot in identities:
                inventory.update(f"{cell}:{crop_identity(snapshot)}\n".encode())
                count += 1
            self.fence(session, job)
            session.execute(
                text(
                    "UPDATE symbol_readability_runs SET "
                    "inventory_fingerprint=:fingerprint,item_count=:count,receipt=CAST(:r"
                    "eceipt AS jsonb),status='processing' WHERE game_id=:game AND id=:run"
                ),
                {
                    "game": job.game_id,
                    "run": identifier,
                    "fingerprint": inventory.hexdigest(),
                    "count": count,
                    "receipt": json.dumps(receipt),
                },
            )

    def process(
        self, context: JobExecutionContext, job: Job, identifier: UUID, base: FrozenBase, model: Any
    ) -> None:
        assert job.game_id is not None
        artifact = None
        calibration = load_pinned_calibration(self.root, base)
        with self.factory() as session, session.begin():
            repo = self._repo(session, job)
            run = repo.row("runs", job.game_id, identifier)
            if run["kind"] == "scan":
                record = repo.row("models", job.game_id, run["model_id"])
                artifact = load_artifact(
                    long_path_aware(managed_path(self.root, record["artifact_path"])),
                    expected_fingerprint=record["fingerprint"],
                    base=base,
                )
        while True:
            with self.factory() as session, session.begin():
                repo = self._repo(session, job)
                repo.acquire_write_lock(job.game_id)
                source = session.scalar(
                    text(
                        "SELECT source_id FROM symbol_readability_items WHERE game_id=:game "
                        "AND run_id=:run AND NOT processed ORDER BY source_id LIMIT 1"
                    ),
                    {"game": job.game_id, "run": identifier},
                )
                if source is None:
                    self.fence(session, job)
                    session.execute(
                        text(
                            "UPDATE symbol_readability_runs SET status='completed' WHERE "
                            "game_id=:game AND id=:run"
                        ),
                        {"game": job.game_id, "run": identifier},
                    )
                    return
                items = (
                    session.execute(
                        text(
                            "SELECT * FROM symbol_readability_items WHERE game_id=:game AND "
                            "run_id=:run AND source_id=:source AND NOT processed ORDER BY "
                            "sequence_number,cell_index"
                        ),
                        {"game": job.game_id, "run": identifier, "source": source},
                    )
                    .mappings()
                    .all()
                )
                # Identity is rechecked and rows are written in this same source transaction.
                error_count = 0
                review_count = 0
                crops = []
                valid = []
                loader = CanonicalSourceLoader(allow_crop=True)
                try:
                    frame = None
                    source_error: CanonicalSourceLoadError | ReadabilityError | None = None
                    for item in items:
                        row = item["snapshot"]
                        current = repo.current(job.game_id, item["cell_id"], lock=True)
                        if not identity_is_current(row, current):
                            review_count += 1
                            self._result(
                                session,
                                job.game_id,
                                identifier,
                                dict(item),
                                "stale",
                                ["crop_identity_changed"],
                            )
                            continue
                        if row["asset_mode"] == "none" or row.get("source_visibility") == "outside":
                            review_count += 1
                            self._result(
                                session, job.game_id, identifier, dict(item), "skipped", ["outside"]
                            )
                            continue
                        try:
                            if source_error is not None:
                                raise source_error
                            if frame is None:
                                try:
                                    frame = loader.load(
                                        managed_source_path(self.root, row["source_sha256"]),
                                        expected_source_checksum_sha256=row["source_sha256"],
                                    )
                                except (CanonicalSourceLoadError, ReadabilityError) as error:
                                    source_error = error
                                    raise
                            if (
                                frame.source.normalized_pixel_checksum_sha256
                                != row["normalized_pixel_checksum_sha256"]
                            ):
                                source_error = ReadabilityError(
                                    "READABILITY_SOURCE_PIXEL_DRIFT", "Source pixels differ."
                                )
                                raise source_error
                            rgb = self.render_snapshot(session, job.game_id, row, frame)
                            crops.append(rgb)
                            valid.append(item)
                        except (
                            CellRenderSpecError,
                            CanonicalSourceLoadError,
                            VirtualCellExtractionError,
                            ReadabilityError,
                        ) as error:
                            error_count += 1
                            self._result(
                                session, job.game_id, identifier, dict(item), "error", [error.code]
                            )
                    if crops:
                        features = extract_source_features(model, crops)
                        scores = None if artifact is None else artifact.score(features)
                        top1 = pinned_top1(model, crops, calibration)
                        for index, item in enumerate(valid):
                            first = None if scores is None else float(scores[0][index])
                            second = None if scores is None else float(scores[1][index])
                            primary_margin = None
                            secondary_margin = None
                            reasons = []
                            if artifact is not None:
                                assert first is not None and second is not None
                                primary_margin = max(
                                    first - artifact.overlap.threshold,
                                    second - artifact.unreadable.threshold,
                                )
                                secondary_margin = min(
                                    first - artifact.overlap.threshold,
                                    second - artifact.unreadable.threshold,
                                )
                                if first is not None and first > artifact.overlap.threshold:
                                    reasons.append("overlap_score")
                                if second is not None and second > artifact.unreadable.threshold:
                                    reasons.append("unreadable_score")
                            session.execute(
                                text(
                                    "UPDATE symbol_readability_items SET "
                                    "identity=:identity,processed=true,features=CAST(:features AS "
                                    "jsonb),snapshot=CAST(:snapshot AS jsonb),rank_margin=:margin,"
                                    "rank_secondary=:secondary,overlap_scor"
                                    "e=:first,unreadable_score=:second,candidate=:cand"
                                    "idate,reasons=CAST(:reasons AS jsonb) WHERE game_id=:game AND "
                                    "run_id=:run AND cell_id=:cell"
                                ),
                                {
                                    "game": job.game_id,
                                    "run": identifier,
                                    "cell": item["cell_id"],
                                    "identity": crop_identity(item["snapshot"]),
                                    "snapshot": json.dumps(
                                        {
                                            **item["snapshot"],
                                            "quality_top1": top1[index],
                                            "confidence_provenance": PROVENANCE
                                            if calibration is not None
                                            else None,
                                        }
                                    ),
                                    "features": json.dumps(features[index].tolist())
                                    if artifact is None
                                    else None,
                                    "first": first,
                                    "second": second,
                                    "candidate": bool(reasons),
                                    "margin": primary_margin,
                                    "secondary": secondary_margin,
                                    "reasons": json.dumps(reasons),
                                },
                            )
                finally:
                    loader.clear()
                self.fence(session, job)
                run = repo.row("runs", job.game_id, identifier)
                receipt = {
                    **run["receipt"],
                    "successCount": run["receipt"].get("successCount", 0) + len(valid),
                    "failureCount": run["receipt"].get("failureCount", 0) + error_count,
                    "reviewCount": run["receipt"].get("reviewCount", 0) + review_count,
                }
                session.execute(
                    text(
                        "UPDATE symbol_readability_runs SET "
                        "processed_count=processed_count+:count,receipt=CAST(:receipt AS "
                        "jsonb) WHERE game_id=:game AND id=:run"
                    ),
                    {
                        "game": job.game_id,
                        "run": identifier,
                        "count": len(items),
                        "receipt": json.dumps(receipt),
                    },
                )
                run = repo.row("runs", job.game_id, identifier)
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "run_id": str(identifier),
                    "source_id": str(source),
                    "inventoryFingerprint": run["inventory_fingerprint"],
                },
                stage="readability_source",
                current=run["processed_count"],
                total=run["item_count"],
                success_count=receipt["successCount"],
                failure_count=receipt["failureCount"],
                review_count=receipt["reviewCount"],
            )

    @staticmethod
    def _result(
        session: Session,
        game: UUID,
        run: UUID,
        item: Mapping[str, Any],
        state: str,
        reasons: list[str],
    ) -> None:
        session.execute(
            text(
                "UPDATE symbol_readability_items SET "
                "identity=:identity,processed=true,state=:state,reasons=CAST(:reasons"
                " AS jsonb) WHERE game_id=:game AND run_id=:run AND cell_id=:cell"
            ),
            {
                "game": game,
                "run": run,
                "cell": item["cell_id"],
                "identity": crop_identity(item["snapshot"]),
                "state": state,
                "reasons": json.dumps(reasons),
            },
        )

    def render_snapshot(
        self, session: Session, game: UUID, row: Mapping[str, Any], frame: Any
    ) -> Any:
        key = CellRenderSpecKey(
            UUID(row["recognized_board_id"]),
            row["geometry_revision"],
            row["cell_index"],
            row["render_spec_checksum_sha256"],
        )
        spec = load_cell_render_specs(session, game_id=game, keys=[key])[key]
        rgb = render_persisted_virtual_cell_rgb(
            frame,
            render_spec=spec,
            expected_render_spec_checksum_sha256=row["render_spec_checksum_sha256"],
            expected_rendered_pixel_checksum_sha256=row["rendered_pixel_checksum_sha256"],
            expected_cell_index=row["cell_index"],
            expected_row_index=row["row_index"],
            expected_column_index=row["column_index"],
            expected_logical_cell_key_sha256=row["logical_cell_key"],
            expected_logical_cell_key_v2_sha256=row["logical_cell_key_v2"],
            expected_extractor_version=row["extractor_version"],
        )
        return rgb

    def verify_pilot_assets(
        self, session: Session, game: UUID, items: Sequence[Mapping[str, Any]]
    ) -> None:
        loader = CanonicalSourceLoader(allow_crop=True)
        try:
            previous = None
            frame = None
            for item in sorted(items, key=lambda value: str(value["source_id"])):
                row = item["snapshot"]
                if previous != row["source_id"]:
                    loader.clear()
                    frame = loader.load(
                        managed_source_path(self.root, row["source_sha256"]),
                        expected_source_checksum_sha256=row["source_sha256"],
                    )
                    previous = row["source_id"]
                self.render_snapshot(session, game, row, frame)
        except (CanonicalSourceLoadError, VirtualCellExtractionError, CellRenderSpecError) as error:
            raise ReadabilityError("READABILITY_PILOT_PIXEL_DRIFT", str(error)) from error
        finally:
            loader.clear()

    def fit(
        self, context: JobExecutionContext, job: Job, identifier: UUID, base: FrozenBase
    ) -> None:
        assert job.game_id is not None
        with self.factory() as session, session.begin():
            repo = self._repo(session, job)
            record = repo.row("models", job.game_id, identifier)
            if record["job_id"] != job.id:
                raise ReadabilityError("READABILITY_JOB_INVALID", "Model/job binding differs.")
            if record["status"] == "completed":
                return
            run = repo.row("runs", job.game_id, record["pilot_run_id"])
            if run["revision"] != record["pilot_revision"]:
                raise ReadabilityError(
                    "READABILITY_COHORT_DRIFT", "Pilot labels changed after fit was requested."
                )
            items = (
                session.execute(
                    text(
                        "SELECT * FROM symbol_readability_items WHERE game_id=:game AND "
                        "run_id=:run ORDER BY cell_id"
                    ),
                    {"game": job.game_id, "run": run["id"]},
                )
                .mappings()
                .all()
            )
            if len(items) != 800 or any(
                item["state"] in {"stale", "error", "skipped"} or item["features"] is None
                for item in items
            ):
                raise ReadabilityError(
                    "READABILITY_PILOT_STOP", "Pilot inventory incomplete or stale."
                )
            self.verify_pilot_assets(session, job.game_id, [dict(item) for item in items])
            samples = [sample_from_item(dict(item)) for item in items]
            assignments: list[Split] = []
            for item in items:
                part = "audit" if item["sample_kind"] == "audit" else item["snapshot"]["head_split"]
                if part not in {"train", "validation", "test", "audit"}:
                    raise ReadabilityError("READABILITY_SPLIT_INVALID", "Frozen split is invalid.")
                assignments.append(cast(Split, part))
            # Known recording exposure is an additional boundary beyond the base's aliases.
            for sample, part in zip(samples, assignments, strict=True):
                exposure = set(run["receipt"]["baseRecordings"].get(sample.recording_id, []))
                if (
                    part in {"test", "audit"}
                    and exposure & {"train", "validation"}
                    or part in {"train", "validation"}
                    and exposure & {"test", "regression"}
                ):
                    raise ReadabilityError(
                        "READABILITY_SPLIT_LEAKAGE", "Known recording crosses base/head split."
                    )
            cohort = assign_families(samples, base, assignments=assignments)
            features = np.asarray([item["features"] for item in items], dtype=np.float64)
            artifact = train_detector(cohort, features, base)
            receipt = run["receipt"]
            report = evaluate_pilot(artifact, cohort, features, natural_audit_receipt=receipt)
            report["confidenceProvenance"] = (
                PROVENANCE
                if all(
                    item["snapshot"].get("confidence_provenance") == PROVENANCE for item in items
                )
                else None
            )
            path = publish_quality_artifact(self.root, job.game_id, identifier, artifact.document())
            repo.acquire_write_lock(job.game_id)
            self.fence(session, job)
            current_model = repo.row("models", job.game_id, identifier, lock=True)
            current_run = repo.row("runs", job.game_id, record["pilot_run_id"], lock=True)
            if current_run["revision"] != current_model["pilot_revision"]:
                raise ReadabilityError("READABILITY_COHORT_DRIFT", "Pilot changed during fit.")
            repo._refresh_stale(job.game_id, current_run["id"])
            if session.scalar(
                text(
                    "SELECT count(*) FROM symbol_readability_items WHERE "
                    "game_id=:game AND run_id=:run AND state='stale'"
                ),
                {"game": job.game_id, "run": current_run["id"]},
            ):
                raise ReadabilityError(
                    "READABILITY_COHORT_DRIFT", "Pilot pixels changed during fit."
                )
            session.execute(
                text(
                    "UPDATE symbol_readability_models SET "
                    "status='completed',fingerprint=:fingerprint,artifact_path=:path,repo"
                    "rt=CAST(:report AS jsonb),revision=revision+1 WHERE game_id=:game "
                    "AND id=:id"
                ),
                {
                    "game": job.game_id,
                    "id": identifier,
                    "fingerprint": artifact.document()["fingerprint"],
                    "path": path,
                    "report": json.dumps(report),
                },
            )
        context.checkpoint(
            checkpoint_payload={
                "schema_version": 1,
                "model_id": str(identifier),
                "artifactFingerprint": artifact.document()["fingerprint"],
            },
            stage="readability_fit",
            current=1,
            total=1,
            success_count=1 if report["status"] == "PASS" else 0,
            failure_count=0,
            review_count=0 if report["status"] == "PASS" else 1,
        )
