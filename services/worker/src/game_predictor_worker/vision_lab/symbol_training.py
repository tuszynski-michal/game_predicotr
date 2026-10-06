"""Fresh bounded CNN training using neutral v2 epoch checkpoints and lab fencing."""

import io
import json
import random
import time
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision.transforms import functional  # type: ignore[import-untyped]

from game_predictor_worker.images.symbol_classifier import load_image_tensor
from game_predictor_worker.images.symbol_model_benchmark import (
    SpatialSymbolCnn,
    augment_training_tensor,
)
from game_predictor_worker.training_core.checkpoint import (
    checkpoint_bytes,
    load_checkpoint,
    make_checkpoint,
    restore_checkpoint,
)

from .run_contracts import StartRunRequest
from .run_files import verify_artifact
from .runs import checkpoint_binding
from .symbol_augmentation import VERSION as ROBUST_AUGMENTATION
from .symbol_augmentation import augment as augment_appearance
from .symbol_models import AI_MODELS, FEEDBACK_MODELS, ROBUST_MODELS, metrics, probabilities
from .symbol_training_manifest import SymbolTrainingInputs
from .training_adapter import RunControl


class SymbolDataset(Dataset[tuple[torch.Tensor, int]]):
    def __init__(
        self,
        inputs: SymbolTrainingInputs,
        partition: str,
        gray: bool,
        seed: int,
        robust: bool = False,
    ):
        self.gray, self.seed, self.epoch = gray, seed, 0
        self.robust = robust
        self.feedback_ids = set(inputs.payload.get("feedback_sample_ids", []))
        entries = inputs.preparation["dictionary"]["entries"]
        ids = {entry["id"]: index for index, entry in enumerate(entries)}
        self.samples = [
            s["decision"]
            for s in inputs.preparation["samples"]
            if (partition == "ai_audit" and s.get("ai_audit") is True)
            or (
                partition != "ai_audit"
                and not s.get("ai_audit", False)
                and inputs.payload["assignments"][s["decision"]["binding"]["source_id"]]
                == partition
            )
        ]
        self.tensors = [
            load_image_tensor(inputs.bundle / "crops" / (s["binding"]["byte_sha256"] + ".png"), 64)
            for s in self.samples
        ]
        self.labels = [ids[s["symbol_id"]] for s in self.samples]

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        tensor = self.tensors[index].clone()
        if self.epoch:
            augment = augment_appearance if self.robust else augment_training_tensor
            tensor = augment(
                tensor,
                sample_id=self.samples[index]["decision_id"],
                seed=self.seed,
                epoch=self.epoch,
            )
        if self.gray:
            tensor = functional.rgb_to_grayscale(tensor, num_output_channels=3)
        return tensor, self.labels[index]


def training_loader(
    data: SymbolDataset, batch_size: int, generator: torch.Generator, *, feedback: bool = False
) -> DataLoader[tuple[torch.Tensor, int]]:
    """Use the checkpointed generator for both weighted draws and loader state."""
    if feedback:
        weights = [4 if s["decision_id"] in data.feedback_ids else 1 for s in data.samples]
        sampler = WeightedRandomSampler(
            weights, num_samples=sum(weights), replacement=True, generator=generator
        )
        return DataLoader(
            data, batch_size=batch_size, sampler=sampler, generator=generator, num_workers=0
        )
    return DataLoader(data, batch_size=batch_size, shuffle=True, generator=generator, num_workers=0)


def evaluate(
    model: torch.nn.Module, data: SymbolDataset, batch_size: int, device: torch.device
) -> np.ndarray:
    model.eval()
    rows = []
    with torch.no_grad():
        for images, _ in DataLoader(data, batch_size=batch_size, shuffle=False, num_workers=0):
            rows.extend(model(images.to(device)).cpu().tolist())
    return np.asarray(rows, dtype=np.float64)


def preferred(candidate: dict[str, Any], best: dict[str, Any] | None) -> bool:
    return best is None or (
        -candidate["metrics"]["macro_accuracy"],
        candidate["metrics"]["log_loss"],
        candidate["epoch"],
    ) < (-best["metrics"]["macro_accuracy"], best["metrics"]["log_loss"], best["epoch"])


def export_onnx(
    model: torch.nn.Module, dataset: SymbolDataset, control: RunControl
) -> dict[str, Any]:
    # Optional dependencies are inspected before export; numerical failures are never hidden.
    from importlib.util import find_spec

    if find_spec("onnx") is None or find_spec("onnxruntime") is None:
        return {"status": "unavailable", "reason": "onnx/onnxruntime absent in pinned runtime"}
    import onnxruntime as ort  # type: ignore[import-untyped]

    model.cpu().eval()
    example = torch.stack([dataset[0][0], dataset[1][0]])
    buffer = io.BytesIO()
    torch.onnx.export(
        model,
        example,
        buffer,
        input_names=["images"],
        output_names=["logits"],
        dynamic_axes={"images": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    session = ort.InferenceSession(buffer.getvalue(), providers=["CPUExecutionProvider"])
    error = 0.0
    for offset in range(0, len(dataset), 32):
        batch = torch.stack([dataset[i][0] for i in range(offset, min(offset + 32, len(dataset)))])
        with torch.no_grad():
            expected = model(batch).numpy()
        observed = session.run(None, {"images": batch.numpy()})[0]
        error = max(error, float(np.abs(expected - observed).max()))
        if error > 1e-4 or not np.array_equal(expected.argmax(1), observed.argmax(1)):
            raise ValueError("SYMBOL_ONNX_PARITY_FAILED")
    artifact = control.manager.publish_artifact(
        control.run_id, control.lease, "onnx", buffer.getvalue()
    )
    return {
        "status": "passed",
        "max_absolute_error": error,
        "samples": len(dataset),
        "artifact": artifact.model_dump(),
    }


def train(
    inputs: SymbolTrainingInputs,
    request: StartRunRequest,
    control: RunControl,
    *,
    device_name: str = "cuda",
) -> dict[str, Any]:
    started = time.monotonic()
    random.seed(request.seed)
    np.random.seed(request.seed)
    torch.manual_seed(request.seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    device = torch.device(device_name)
    gray = request.model_version.endswith(("gray-v1", "gray-v2", "gray-v3", "gray-v4-ai"))
    feedback = request.model_version in FEEDBACK_MODELS
    ai_experiment = request.model_version in AI_MODELS
    if feedback != (inputs.payload.get("purpose") == "symbol_crop_feedback"):
        raise ValueError("SYMBOL_FEEDBACK_GENERATION_BINDING_REQUIRED")
    if ai_experiment != (inputs.payload.get("purpose") == "symbol_ai_experiment"):
        raise ValueError("SYMBOL_AI_GENERATION_BINDING_REQUIRED")
    robust = request.model_version in (*ROBUST_MODELS, *FEEDBACK_MODELS, *AI_MODELS)
    classes = [entry["display_name"] for entry in inputs.preparation["dictionary"]["entries"]]
    train_data = SymbolDataset(inputs, "development", gray, request.seed, robust=robust)
    val_data = SymbolDataset(inputs, "validation", gray, request.seed)
    generator = torch.Generator().manual_seed(request.seed)
    model = SpatialSymbolCnn(len(classes))
    # For the fixed64 input, the last feature map is16x16. Non-overlapping average
    # pooling is numerically equivalent to adaptive4x4 pooling and has a deterministic
    # CUDA backward implementation. Keep the existing production architecture untouched.
    model.features[-1] = torch.nn.AvgPool2d(kernel_size=4, stride=4)
    model = model.to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=request.configuration.learning_rate, weight_decay=0.0001
    )
    run = control.manager.detail(control.run_id)
    binding = checkpoint_binding(request)
    start_epoch, global_step, history, best = 0, 0, [], None
    if run.checkpoint is not None:
        path = verify_artifact(control.manager.root, run.checkpoint)
        value = load_checkpoint(path, run.checkpoint.sha256, expected_binding=binding)
        restore_checkpoint(value, model, optimizer, None, generator)
        start_epoch, global_step, history, best = (
            value["epoch"],
            value["globalStep"],
            value["history"],
            value.get("bestState"),
        )

    def save(epoch: int) -> None:
        value = make_checkpoint(
            model,
            optimizer,
            None,
            generator,
            binding=binding,
            epoch=epoch,
            global_step=global_step,
            history=history,
            best_state=best,
        )
        control.checkpoint(checkpoint_bytes(value), epoch)

    if run.checkpoint is None:
        save(0)
    for epoch in range(start_epoch + 1, request.configuration.epochs + 1):
        train_data.epoch = epoch
        model.train()
        loader = training_loader(
            train_data,
            request.configuration.batch_size,
            generator,
            feedback=feedback or ai_experiment,
        )
        for images, labels in loader:
            control.before_batch()
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.cross_entropy(model(images.to(device)), labels.to(device))
            loss.backward()  # type: ignore[no-untyped-call]
            optimizer.step()
            global_step += 1
            control.after_batch()
        train_data.epoch = 0
        val_logits = evaluate(model, val_data, request.configuration.batch_size, device)
        measured = metrics(probabilities(val_logits), val_data.labels, classes)
        candidate = {"epoch": epoch, "metrics": measured}
        if preferred(candidate, best):
            best = {
                **candidate,
                "weights": {
                    key: value.detach().cpu().clone() for key, value in model.state_dict().items()
                },
            }
        history.append(candidate)
        save(epoch)
        if best is None:
            raise ValueError("SYMBOL_BEST_MODEL_MISSING")
        print(
            json.dumps(
                {
                    "epoch": epoch,
                    "validation_accuracy": measured["accuracy"],
                    "macro_accuracy": measured["macro_accuracy"],
                    "best_epoch": best["epoch"],
                }
            ),
            flush=True,
        )
    if best is None:
        raise ValueError("SYMBOL_BEST_MODEL_MISSING")
    model.load_state_dict(best["weights"])
    val_logits = evaluate(model, val_data, request.configuration.batch_size, device)
    train_logits = evaluate(model, train_data, request.configuration.batch_size, device)
    validation = metrics(probabilities(val_logits), val_data.labels, classes)
    development = metrics(probabilities(train_logits), train_data.labels, classes)
    weights = checkpoint_bytes(
        {
            "format": "lab-symbol-best-v1",
            "binding": binding,
            "classes": classes,
            "epoch": best["epoch"],
            "modelState": best["weights"],
        }
    )
    control.manager.publish_artifact(control.run_id, control.lease, "best_weights", weights)
    predictions = {
        "manifest_id": inputs.manifest_id,
        "classes": classes,
        "labels": val_data.labels,
        "sample_ids": [s["decision_id"] for s in val_data.samples],
        "logits": val_logits.tolist(),
    }
    extra: dict[str, Any] = {}
    if feedback or ai_experiment:
        indices = [
            i
            for i, s in enumerate(train_data.samples)
            if s["decision_id"] in train_data.feedback_ids
        ]
        diagnostic_data = SymbolDataset(inputs, "diagnostic_test", gray, request.seed)
        diagnostic_logits = evaluate(
            model, diagnostic_data, request.configuration.batch_size, device
        )

        def result(logits: np.ndarray, labels: list[int], sample_ids: list[str]) -> dict[str, Any]:
            return {
                "metrics": metrics(probabilities(logits), labels, classes),
                "predictions": {
                    "manifest_id": inputs.manifest_id,
                    "classes": classes,
                    "labels": labels,
                    "sample_ids": sample_ids,
                    "logits": logits.tolist(),
                },
            }

        extra = {
            "feedback_regression": {
                **result(
                    train_logits[indices],
                    [train_data.labels[i] for i in indices],
                    [train_data.samples[i]["decision_id"] for i in indices],
                ),
                "exposure": "development training targets; not an independent test",
            },
            "diagnostic_test": {
                **result(
                    diagnostic_logits,
                    diagnostic_data.labels,
                    [s["decision_id"] for s in diagnostic_data.samples],
                ),
                "evaluated_after_model_selection": True,
                "exposure": (
                    "excluded from this training; older models saw these labels; two classes only"
                ),
            },
            "sampling": {
                "policy": "feedback-weight4-replacement-v1",
                "feedback_weight": 4,
                "unique_development": len(train_data),
                "feedback_samples": len(indices),
                "draws_per_epoch": len(train_data) + 3 * len(indices),
            },
        }
    if ai_experiment:
        audit_data = SymbolDataset(inputs, "ai_audit", gray, request.seed)
        audit_logits = evaluate(model, audit_data, request.configuration.batch_size, device)
        ai_indices = [
            i for i, s in enumerate(train_data.samples) if s.get("origin") == "ai_visual_assessment"
        ]
        extra["ai_experiment"] = {
            "origin": "ai_visual_assessment",
            "human_labels_written": 0,
            "ai_training_samples": len(ai_indices),
            "ai_training_agreement": result(
                train_logits[ai_indices],
                [train_data.labels[i] for i in ai_indices],
                [train_data.samples[i]["decision_id"] for i in ai_indices],
            ),
            "withheld_ai_agreement": result(
                audit_logits, audit_data.labels, [s["decision_id"] for s in audit_data.samples]
            ),
            "evaluated_after_model_selection": True,
            "limitation": (
                "AI consensus is fallible; same-film audit is not "
                "human accuracy or independent film test"
            ),
        }
        extra["sampling"]["policy"] = "human-feedback4-ai1-replacement-v1"
        extra["sampling"]["ai_weight"] = 1
        extra["sampling"]["ai_samples"] = len(ai_indices)
    onnx = export_onnx(model, val_data, control)
    return {
        "model_version": request.model_version,
        "manifest_id": inputs.manifest_id,
        "best_epoch": best["epoch"],
        "completed_epochs": request.configuration.epochs,
        "development": development,
        "validation": validation,
        "accuracy_gap": development["accuracy"] - validation["accuracy"],
        "history": history,
        "predictions": predictions,
        "onnx": onnx,
        "worker_training_seconds": time.monotonic() - started,
        "augmentation": ROBUST_AUGMENTATION if robust else "bounded-affine-color-v1",
        "from_scratch": True,
        "independent_final_test": False,
        "super_labels": 0,
        **extra,
    }
