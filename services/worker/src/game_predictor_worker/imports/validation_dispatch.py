"""Dispatch durable validation jobs by their explicit validation kind."""

from __future__ import annotations

from collections.abc import Callable

from game_predictor_api.domain.jobs import Job

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


class ValidationJobDispatchHandler:
    def __init__(
        self,
        layout_handler: Callable[[JobExecutionContext, Job], None],
        page_geometry_handler: Callable[[JobExecutionContext, Job], None],
    ) -> None:
        self._layout_handler = layout_handler
        self._page_geometry_handler = page_geometry_handler

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        kind = job.input_payload.get("validation_kind")
        if kind == "layout_import":
            self._layout_handler(context, job)
            return
        if kind == "page_geometry_preflight":
            self._page_geometry_handler(context, job)
            return
        raise JobHandlerError(
            "VALIDATION_KIND_UNSUPPORTED",
            "The validate job has an unsupported validation kind.",
        )


__all__ = ["ValidationJobDispatchHandler"]
