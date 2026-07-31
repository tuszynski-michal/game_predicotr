"""Route import jobs to their typed local handlers."""

from collections.abc import Callable

from game_predictor_api.domain.jobs import Job

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


class ImportJobDispatchHandler:
    def __init__(
        self,
        layout_handler: Callable[[JobExecutionContext, Job], None],
        image_handler: Callable[[JobExecutionContext, Job], None],
    ) -> None:
        self._layout_handler = layout_handler
        self._image_handler = image_handler

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        kind = job.input_payload.get("import_kind")
        if kind == "layout_file":
            self._layout_handler(context, job)
            return
        if kind == "image_directory":
            self._image_handler(context, job)
            return
        raise JobHandlerError(
            "IMPORT_KIND_UNSUPPORTED",
            "The import job has an unsupported import kind.",
        )


__all__ = ["ImportJobDispatchHandler"]
