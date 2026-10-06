"""One cached CPU neural engine per job, with a deadline for each source."""

from __future__ import annotations

import multiprocessing
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from .bounded_runtime import Analyser, GeometryRuntimeError
from .inference import BoardDetection, onnx_engine
from .preprocessing import ByteImage


class ConnectionEndpoint(Protocol):
    def send(self, value: object) -> None: ...
    def recv(self) -> object: ...
    def poll(self, timeout: float = 0.0) -> bool: ...
    def close(self) -> None: ...


def _serve(
    connection: ConnectionEndpoint,
    bundle: Path,
    checksum: str,
    threads: int,
    factory: Callable[..., Analyser],
) -> None:
    try:
        engine = factory(bundle, threads=threads, expected_bundle_sha256=checksum)
        connection.send(("ready", None))
        while True:
            rgb = connection.recv()
            if rgb is None:
                return
            connection.send(("ok", engine.analyse(cast(ByteImage, rgb))))
    except EOFError:
        pass
    except Exception as error:
        connection.send(("error", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


class CPUGridProposalRunner:
    """Cache model loading while retaining cancellation, deadlines and child cleanup."""

    def __init__(self, threads: int = 1, *, factory: Callable[..., Analyser] = onnx_engine) -> None:
        if not 1 <= threads <= 64:
            raise ValueError("Neural proposal threads must be between 1 and 64.")
        self._threads = threads
        self._factory = factory
        self._process: multiprocessing.process.BaseProcess | None = None
        self._connection: ConnectionEndpoint | None = None
        self._identity: tuple[Path, str] | None = None
        self._transport: threading.Thread | None = None

    def run(
        self,
        bundle: Path,
        bundle_sha256: str,
        rgb: ByteImage,
        *,
        heartbeat: Callable[[], None],
        max_seconds: float,
    ) -> list[BoardDetection]:
        if not 0 < max_seconds <= 120:
            raise ValueError("A source inference requires a bounded deadline.")
        identity = (bundle.resolve(), bundle_sha256)
        deadline = time.monotonic() + max_seconds
        started = self._process is None
        if started:
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe()
            spawned = context.Process(
                target=_serve,
                args=(child, bundle, bundle_sha256, self._threads, self._factory),
                name="neural-folder-source",
            )
            try:
                spawned.start()
            except BaseException:
                parent.close()
                child.close()
                raise
            child.close()
            self._process, self._connection, self._identity = spawned, parent, identity
        if self._identity != identity:
            self.close()
            raise GeometryRuntimeError(
                "NEURAL_GRID_MODEL_SNAPSHOT_DRIFT",
                "A cached neural engine cannot change model identity.",
            )
        process, connection = self._process, self._connection
        assert process is not None and connection is not None
        finished = threading.Event()
        ready = threading.Event()
        if not started:
            ready.set()
        receipt: list[tuple[str, object]] = []

        def exchange() -> None:
            try:
                if started:
                    status, message = cast(tuple[str, object], connection.recv())
                    if status != "ready":
                        receipt.append(("error", message))
                        return
                    ready.set()
                connection.send(rgb)
                receipt.append(cast(tuple[str, object], connection.recv()))
            except BaseException as error:
                receipt.append(("error", f"{type(error).__name__}: {error}"))
            finally:
                finished.set()

        transport = threading.Thread(target=exchange, name="neural-folder-transport", daemon=True)
        self._transport = transport
        try:
            transport.start()
            next_heartbeat = 0.0
            while True:
                now = time.monotonic()
                if now >= deadline:
                    raise GeometryRuntimeError(
                        "NEURAL_GRID_SOURCE_TIME_LIMIT"
                        if ready.is_set()
                        else "NEURAL_GRID_STARTUP_TIME_LIMIT",
                        "Neural source inference exceeded its deadline.",
                    )
                if now >= next_heartbeat:
                    heartbeat()
                    next_heartbeat = now + 2.0
                if finished.wait(min(0.25, deadline - now)):
                    status, value = receipt[0]
                    if status != "ok":
                        raise GeometryRuntimeError("NEURAL_GRID_RUNTIME_FAILED", str(value))
                    transport.join(timeout=1.0)
                    self._transport = None
                    return cast(list[BoardDetection], value)
                if not process.is_alive():
                    raise GeometryRuntimeError(
                        "NEURAL_GRID_RUNTIME_FAILED", "Neural inference exited without a result."
                    )
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        process, connection = self._process, self._connection
        transport = self._transport
        self._transport = None
        self._process, self._connection, self._identity = None, None, None
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=1.0)
            if process.is_alive():
                raise GeometryRuntimeError(
                    "NEURAL_GRID_RUNTIME_CLEANUP_FAILED", "Neural worker could not be stopped."
                )
            process.close()
        if connection is not None:
            connection.close()
        if transport is not None and transport.ident is not None:
            transport.join(timeout=1.0)
            if transport.is_alive():
                raise GeometryRuntimeError(
                    "NEURAL_GRID_RUNTIME_CLEANUP_FAILED",
                    "The neural transport could not be stopped.",
                )
