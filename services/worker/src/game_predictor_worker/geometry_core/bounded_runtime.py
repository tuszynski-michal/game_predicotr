"""One-source CPU process with an enforced deadline and cooperative cancellation."""

from __future__ import annotations

import multiprocessing
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Protocol, cast

from .inference import BoardDetection, file_sha256, onnx_engine
from .preprocessing import ByteImage


class GeometryRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Analyser(Protocol):
    def analyse(self, rgb: ByteImage) -> list[BoardDetection]: ...


def _infer(
    connection: Connection,
    bundle: Path,
    bundle_sha256: str,
    rgb: ByteImage,
    threads: int,
    factory: Callable[..., Analyser],
) -> None:
    try:
        if file_sha256(bundle / "bundle.json") != bundle_sha256:
            raise ValueError("NEURAL_GRID_BUNDLE_CHECKSUM_MISMATCH")
        engine = factory(bundle, threads=threads, expected_bundle_sha256=bundle_sha256)
        connection.send(("ok", engine.analyse(rgb)))
    except Exception as error:
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


class CPUShadowRunner:
    """Includes model loading in the deadline; always reaps the child process."""

    def __init__(self, threads: int = 1, *, factory: Callable[..., Analyser] = onnx_engine) -> None:
        self._threads = threads
        self._factory = factory

    def run(
        self,
        bundle: Path,
        bundle_sha256: str,
        rgb: ByteImage,
        *,
        heartbeat: Callable[[], None],
        max_seconds: float,
    ) -> list[BoardDetection]:
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        process = context.Process(
            target=_infer,
            args=(send, bundle, bundle_sha256, rgb, self._threads, self._factory),
            name="grid-shadow-source",
        )
        deadline = time.monotonic() + max_seconds
        next_heartbeat = time.monotonic()
        started = False
        try:
            process.start()
            started = True
            send.close()
            while True:
                now = time.monotonic()
                if now >= deadline:
                    raise GeometryRuntimeError(
                        "GRID_SHADOW_SOURCE_TIME_LIMIT", "CPU inference exceeded its deadline."
                    )
                if now >= next_heartbeat:
                    heartbeat()
                    next_heartbeat = now + 2.0
                if receive.poll(min(0.25, deadline - now)):
                    try:
                        status, value = receive.recv()
                    except EOFError as error:
                        raise GeometryRuntimeError(
                            "GRID_SHADOW_RUNTIME_FAILED", "CPU inference exited without a result."
                        ) from error
                    if status != "ok":
                        raise GeometryRuntimeError("GRID_SHADOW_RUNTIME_FAILED", str(value))
                    process.join(timeout=min(1.0, max(0.0, deadline - time.monotonic())))
                    if process.is_alive() or process.exitcode != 0:
                        raise GeometryRuntimeError(
                            "GRID_SHADOW_RUNTIME_FAILED", "CPU inference did not finish cleanly."
                        )
                    return cast(list[BoardDetection], value)
                if not process.is_alive():
                    raise GeometryRuntimeError(
                        "GRID_SHADOW_RUNTIME_FAILED", "CPU inference exited without a result."
                    )
        finally:
            send.close()
            receive.close()
            if started:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1.0)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1.0)
                if process.is_alive():
                    raise GeometryRuntimeError(
                        "GRID_SHADOW_RUNTIME_CLEANUP_FAILED", "CPU inference could not be stopped."
                    )
                process.close()


__all__ = ["CPUShadowRunner", "GeometryRuntimeError"]
