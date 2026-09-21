"""Local Admin routes for V7 numeric-label geometry calibration."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from game_predictor_api.application.v7_label_geometry_calibration import (
    V7LabelGeometryCalibrationService,
    V7LabelGeometryProfileRecord,
)
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.v7_label_geometry_calibration import (
    V7LabelGeometryAdoptionCreate,
    V7LabelGeometryAdoptionListResponse,
    V7LabelGeometryAdoptionMutationResponse,
    V7LabelGeometryAdoptionResponse,
    V7LabelGeometryProfileListResponse,
    V7LabelGeometryProfileResponse,
    V7LabelGeometrySessionCreate,
    V7LabelGeometrySessionExportRequest,
    V7LabelGeometrySessionExportResponse,
    V7LabelGeometrySessionMutation,
    V7LabelGeometrySessionMutationResponse,
    V7LabelGeometrySessionResponse,
    V7ValidationReportCreate,
    V7ValidationReportResponse,
)

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {
        "model": ErrorResponse,
        "description": "Calibration session, source, or profile not found",
    },
    409: {"model": ErrorResponse, "description": "Calibration session or source conflict"},
    422: {"model": ErrorResponse, "description": "Invalid calibration request"},
}


def create_v7_label_geometry_calibration_router(
    service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/admin/v7-label-geometry",
        tags=["v7-label-geometry"],
    )
    service_parameter = Depends(service_dependency)

    @router.post(
        "/sessions",
        response_model=V7LabelGeometrySessionResponse,
        operation_id="createV7LabelGeometryCalibrationSession",
        responses=ERROR_RESPONSES,
    )
    def create_session(
        payload: V7LabelGeometrySessionCreate,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometrySessionResponse:
        return _session_response(
            service.create_session(
                geometry_family_id=payload.geometry_family_id,
                corpus_case_ids=tuple(payload.corpus_case_ids),
            )
        )

    @router.get(
        "/sessions/{session_id}",
        response_model=V7LabelGeometrySessionResponse,
        operation_id="getV7LabelGeometryCalibrationSession",
        responses=ERROR_RESPONSES,
    )
    def get_session(
        session_id: str,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometrySessionResponse:
        return _session_response(service.get_session(session_id))

    @router.post(
        "/sessions/{session_id}/operations",
        response_model=V7LabelGeometrySessionMutationResponse,
        operation_id="mutateV7LabelGeometryCalibrationSession",
        responses=ERROR_RESPONSES,
    )
    def mutate_session(
        session_id: str,
        payload: V7LabelGeometrySessionMutation,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometrySessionMutationResponse:
        session, receipt = service.mutate_session(
            session_id,
            service.operation_from_values(
                operation_id=payload.operation_id,
                expected_revision=payload.expected_revision,
                kind=payload.kind,
                source_id=payload.source_id,
                position_index=payload.position_index,
                center_x=payload.center_x,
                center_y=payload.center_y,
                crop_assessment=payload.crop_assessment,
                capture_group_id=payload.capture_group_id,
            ),
        )
        return V7LabelGeometrySessionMutationResponse(
            session=_session_response(session),
            receipt={
                "operationId": receipt.operation_id,
                "operationFingerprint": receipt.operation_fingerprint,
                "revision": receipt.revision,
            },
        )

    @router.get(
        "/sessions/{session_id}/sources/{source_id}/asset",
        response_class=Response,
        operation_id="getV7LabelGeometryCalibrationSourceAsset",
        responses=ERROR_RESPONSES,
    )
    def canonical_asset(
        session_id: str,
        source_id: str,
        expected_source_checksum_sha256: Annotated[
            str,
            Query(alias="expectedSourceChecksumSha256", pattern=r"^[0-9a-f]{64}$"),
        ],
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> Response:
        asset = service.canonical_asset(
            session_id,
            source_id,
            expected_source_checksum_sha256=expected_source_checksum_sha256,
        )
        return Response(
            content=asset.content,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-Source-Checksum-Sha256": asset.source_checksum_sha256,
                "X-Canonical-Image-Height": str(asset.height),
                "X-Canonical-Image-Width": str(asset.width),
            },
        )

    @router.post(
        "/sessions/{session_id}/exports",
        response_model=V7LabelGeometrySessionExportResponse,
        operation_id="exportV7LabelGeometryCalibrationSession",
        responses=ERROR_RESPONSES,
    )
    def export_session(
        session_id: str,
        payload: V7LabelGeometrySessionExportRequest,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometrySessionExportResponse:
        exported = service.export_session(session_id, expected_revision=payload.expected_revision)
        return V7LabelGeometrySessionExportResponse(
            export_checksum_sha256=exported.export_checksum_sha256,
            revision=exported.revision,
        )

    @router.post(
        "/sessions/{session_id}/profiles",
        response_model=V7LabelGeometryProfileResponse,
        operation_id="createV7LabelGeometryProfile",
        responses=ERROR_RESPONSES,
    )
    def create_profile(
        session_id: str,
        payload: V7LabelGeometrySessionExportRequest,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometryProfileResponse:
        return _profile_response(
            service.create_profile(session_id, expected_revision=payload.expected_revision)
        )

    @router.get(
        "/profiles",
        response_model=V7LabelGeometryProfileListResponse,
        operation_id="listV7LabelGeometryProfiles",
        responses=ERROR_RESPONSES,
    )
    def list_profiles(
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometryProfileListResponse:
        return V7LabelGeometryProfileListResponse(
            items=[_profile_response(item) for item in service.list_profiles()]
        )

    @router.get(
        "/profiles/{profile_fingerprint}",
        response_model=V7LabelGeometryProfileResponse,
        operation_id="getV7LabelGeometryProfile",
        responses=ERROR_RESPONSES,
    )
    def get_profile(
        profile_fingerprint: str,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometryProfileResponse:
        return _profile_response(service.get_profile(profile_fingerprint))

    @router.get(
        "/adoptions",
        response_model=V7LabelGeometryAdoptionListResponse,
        operation_id="listV7LabelGeometryAdoptions",
        responses=ERROR_RESPONSES,
    )
    def list_adoptions(
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometryAdoptionListResponse:
        return V7LabelGeometryAdoptionListResponse(
            items=[_adoption_response(item) for item in service.list_adoptions()]
        )

    @router.post(
        "/validation-reports",
        response_model=V7ValidationReportResponse,
        operation_id="createV7LabelGeometryValidationReport",
        responses=ERROR_RESPONSES,
    )
    def create_validation_report(
        payload: V7ValidationReportCreate,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7ValidationReportResponse:
        report, created = service.create_validation_report(
            operation_id=payload.operation_id,
            profile_fingerprint=payload.profile_fingerprint,
            source_game_ref=payload.source_game_ref,
            truth_values=tuple(item.model_dump(by_alias=True) for item in payload.truth),
            source_observation_values=tuple(
                item.model_dump(by_alias=True) for item in payload.source_observations
            ),
            prediction_snapshot_values=tuple(
                item.model_dump(by_alias=True) for item in payload.prediction_snapshots
            ),
        )
        return _validation_report_response(report, created=created)

    @router.post(
        "/adoptions",
        response_model=V7LabelGeometryAdoptionMutationResponse,
        operation_id="createV7LabelGeometryAdoption",
        responses=ERROR_RESPONSES,
    )
    def create_adoption(
        payload: V7LabelGeometryAdoptionCreate,
        service: Annotated[V7LabelGeometryCalibrationService, service_parameter],
    ) -> V7LabelGeometryAdoptionMutationResponse:
        adoption, created = service.create_adoption(
            operation_id=payload.operation_id,
            profile_fingerprint=payload.profile_fingerprint,
            source_game_ref=payload.source_game_ref,
            validation_report_fingerprint=payload.validation_report_fingerprint,
        )
        return V7LabelGeometryAdoptionMutationResponse(
            adoption=_adoption_response(adoption),
            created=created,
        )

    return router


def _session_response(session: object) -> V7LabelGeometrySessionResponse:
    value = session.as_dict()  # type: ignore[attr-defined]
    return V7LabelGeometrySessionResponse(
        session_id=value["sessionId"],
        revision=value["revision"],
        manifest_fingerprint=value["manifestFingerprint"],
        geometry_family_id=value["geometryFamilyId"],
        status=value["status"],
        sources=value["sources"],
        slots=value["slots"],
        capture_groups={
            item["sourceId"]: item["captureGroupId"] for item in value["captureGroups"]
        },
    )


def _profile_response(record: V7LabelGeometryProfileRecord) -> V7LabelGeometryProfileResponse:
    value = record.as_dict()
    return V7LabelGeometryProfileResponse(
        profile_fingerprint=value["profileFingerprint"],
        revision=value["revision"],
        session_export_checksum_sha256=value["sessionExportChecksumSha256"],
        calibration=value["calibration"],
    )


def _validation_report_response(
    report: object,
    *,
    created: bool,
) -> V7ValidationReportResponse:
    value = report.as_dict()  # type: ignore[attr-defined]
    return V7ValidationReportResponse(
        validation_report_fingerprint=value["validationReportFingerprint"],
        profile_fingerprint=value["profileFingerprint"],
        observer_fingerprint=value["observerFingerprint"],
        geometry_family_id=value["geometryFamilyId"],
        source_game_ref=value["sourceGameRef"],
        corpus_manifest_fingerprint=value["corpusManifestFingerprint"],
        corpus_inventory_fingerprint=value["corpusInventoryFingerprint"],
        acceptance=value["acceptance"],
        created=created,
    )


def _adoption_response(value: object) -> V7LabelGeometryAdoptionResponse:
    adoption = value.as_dict()  # type: ignore[attr-defined]
    return V7LabelGeometryAdoptionResponse(
        adoption_key=adoption["adoptionKey"],
        source_game_ref=adoption["sourceGameRef"],
        geometry_family_id=adoption["geometryFamilyId"],
        profile_fingerprint=adoption["profileFingerprint"],
        validation_report_fingerprint=adoption["validationReportFingerprint"],
    )


__all__ = ["create_v7_label_geometry_calibration_router"]
