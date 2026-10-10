"""D-457's single fixed supervised experiment, always mediated by RunControl."""

import random
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from game_predictor_worker.training_core.checkpoint import (
    checkpoint_bytes,
    load_checkpoint,
    make_checkpoint,
    restore_checkpoint,
)
from game_predictor_worker.training_core.runtime import train_epochs

from .hybrid_data import Proposal, corners, matches, normalized_batch, prepare_partition, score
from .hybrid_model import HybridNetwork
from .hybrid_onnx import export_and_check
from .hybrid_protocol import WEIGHTS_FILENAME, protocol, protocol_digest
from .run_contracts import StartRunRequest
from .run_files import verify_artifact
from .runs import checkpoint_binding
from .training_adapter import RunControl
from .training_manifest import TrainingInputs, TrainingTarget


def training_arrays(
    pairs: list[tuple[Proposal, TrainingTarget]], generator: torch.Generator
) -> tuple[torch.Tensor, torch.Tensor]:
    pixels, targets = [], []
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    for p, target in pairs:
        brightness, contrast, scale = torch.rand(3, generator=generator).tolist()
        brightness, contrast, scale = (
            0.9 + brightness * 0.2,
            0.9 + contrast * 0.2,
            0.95 + scale * 0.1,
        )
        image = np.clip((p.pixels - 0.5) * contrast + 0.5, 0, 1) * brightness
        affine = np.array(
            [[scale, 0, 112 * (1 - scale)], [0, scale, 112 * (1 - scale)]], dtype=np.float32
        )
        image = cv2.warpAffine(image, affine, (224, 224), borderValue=(114 / 255,) * 3)
        pixels.append(((np.clip(image, 0, 1) - mean) / std).transpose(2, 0, 1))
        # Both proposal and label undergo exactly the same affine: translation cancels in delta.
        targets.append(
            ((p.normalize(corners(target.nodes)) - p.normalize(p.quad)) * scale).reshape(8)
        )
    return torch.from_numpy(np.asarray(pixels, dtype=np.float32)), torch.from_numpy(
        np.asarray(targets, dtype=np.float32)
    )


def predict(model: HybridNetwork, values: list[Proposal], control: RunControl) -> np.ndarray:
    result = []
    model.eval()
    for start in range(0, len(values), 8):
        control.after_batch()
        with torch.no_grad():
            result.append(
                model(torch.from_numpy(normalized_batch(values[start : start + 8])).cuda())
                .cpu()
                .numpy()
            )
    return np.concatenate(result) if result else np.empty((0, 8), dtype=np.float32)


def fresh_training(
    weights: Path | None, seed: int, device: str = "cuda"
) -> tuple[HybridNetwork, torch.optim.AdamW, torch.Generator]:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    generator = torch.Generator().manual_seed(seed)
    model = HybridNetwork(weights).to(device)
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=0.001, weight_decay=0.0001)
    return model, optimizer, generator


def train(inputs: TrainingInputs, request: StartRunRequest, control: RunControl) -> dict[str, Any]:
    settings = control.manager.settings
    if settings is None:
        raise ValueError("RUN_RUNTIME_NOT_CONFIGURED")
    weights = Path(settings["manifests"]).parent / "cache" / WEIGHTS_FILENAME
    model, optimizer, generator = fresh_training(weights, request.seed)
    history: list[dict[str, Any]] = []
    best: dict[str, Any] = {}
    step, start_epoch = 0, 0
    run = control.manager.detail(control.run_id)
    if run.checkpoint is not None:
        checkpoint = load_checkpoint(
            verify_artifact(control.manager.root, run.checkpoint),
            run.checkpoint.sha256,
            expected_binding=checkpoint_binding(request),
        )
        restore_checkpoint(checkpoint, model, optimizer, None, generator)
        start_epoch, step = checkpoint["epoch"], checkpoint["globalStep"]
        history, best = checkpoint["history"], checkpoint["bestState"]

    def serialize(epoch: int) -> bytes:
        return checkpoint_bytes(
            make_checkpoint(
                model,
                optimizer,
                None,
                generator,
                binding=checkpoint_binding(request),
                epoch=epoch,
                global_step=step,
                history=history,
                best_state=best,
            )
        )

    # Durable initial weights before potentially expensive proposal preparation.
    control.checkpoint(serialize(start_epoch), start_epoch)
    development, train_coverage = prepare_partition(inputs, inputs.development, control.after_batch)
    validation, val_coverage = prepare_partition(inputs, inputs.validation, control.after_batch)
    pairs = [
        (p, target) for p in development for target in inputs.development if matches(p, target)
    ]
    if not pairs or not val_coverage["matched"]:
        raise ValueError("HYBRID_NO_USABLE_PAIRS")
    initial_dev = score(
        inputs.development, development, np.zeros((len(development), 8), dtype=np.float32)
    )
    initial_val = score(
        inputs.validation, validation, np.zeros((len(validation), 8), dtype=np.float32)
    )

    baseline_dev = score(
        inputs.development,
        development,
        np.zeros((len(development), 8), dtype=np.float32),
        original_baseline=True,
    )
    baseline_val = score(
        inputs.validation,
        validation,
        np.zeros((len(validation), 8), dtype=np.float32),
        original_baseline=True,
    )

    def batches(epoch: int) -> Iterator[object]:
        indices = torch.randperm(len(pairs), generator=generator).tolist()
        for start in range(0, len(indices), 8):
            yield training_arrays([pairs[i] for i in indices[start : start + 8]], generator)

    def train_batch(batch: Any) -> None:
        nonlocal step
        model.train()
        pixels, target = batch
        optimizer.zero_grad(set_to_none=True)
        loss = torch.nn.functional.smooth_l1_loss(model(pixels.cuda()), target.cuda(), beta=0.02)
        if not torch.isfinite(loss):
            raise ValueError("HYBRID_LOSS_NONFINITE")
        loss.backward()  # type: ignore[no-untyped-call]
        optimizer.step()
        step += 1

    def finish_epoch(epoch: int) -> None:
        nonlocal best
        metrics = score(inputs.validation, validation, predict(model, validation, control))
        history.append({"epoch": epoch, "validation": metrics})
        if not best or metrics["score"] < best["score"]:
            best = {
                "epoch": epoch,
                "score": metrics["score"],
                "model": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
            }

    train_epochs(
        start_epoch=start_epoch,
        epochs=request.configuration.epochs,
        batches=batches,
        train_batch=train_batch,
        finish_epoch=finish_epoch,
        serialize_checkpoint=serialize,
        control=control,
    )
    if not best:
        raise ValueError("HYBRID_BEST_STATE_MISSING")
    model.load_state_dict(best["model"])
    development_metrics = score(
        inputs.development, development, predict(model, development, control)
    )
    validation_metrics = score(inputs.validation, validation, predict(model, validation, control))
    with tempfile.TemporaryDirectory(prefix="hybrid-export-") as temporary:
        onnx_bytes, best_bytes, parity = export_and_check(
            model, development + validation, Path(temporary) / "model.onnx", control.after_batch
        )
    control.manager.publish_artifact(control.run_id, control.lease, "onnx", onnx_bytes)
    control.manager.publish_artifact(control.run_id, control.lease, "best_weights", best_bytes)
    control.after_batch()
    return {
        "protocol": protocol(),
        "protocol_digest": protocol_digest(),
        "split_fingerprint": inputs.split_fingerprint,
        "best_epoch": best["epoch"],
        "development": development_metrics,
        "validation": validation_metrics,
        "baseline_development": baseline_dev,
        "baseline_validation": baseline_val,
        "initial_homography_development": initial_dev,
        "initial_homography_validation": initial_val,
        "coverage": {"development": train_coverage, "validation": val_coverage},
        "parity": parity,
        "improved_validation": validation_metrics["score"] < baseline_val["score"],
        "gate": "uncalibrated",
        "history": history,
    }
