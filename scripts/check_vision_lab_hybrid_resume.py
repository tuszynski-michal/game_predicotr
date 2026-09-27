"""Tiny synthetic CUDA resume proof. No operator images, registered run or pilot training."""

import io
import json
import os

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import torch
from game_predictor_worker.training_core.checkpoint import (
    checkpoint_bytes,
    make_checkpoint,
    restore_checkpoint,
)
from game_predictor_worker.vision_lab.hybrid_model import HybridNetwork

torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
assert torch.cuda.is_available()
torch.manual_seed(42)
model = HybridNetwork(None).cuda()
optimizer = torch.optim.AdamW(model.head.parameters(), lr=0.001)
generator = torch.Generator().manual_seed(42)


def step(network: HybridNetwork, optim: torch.optim.Optimizer) -> None:
    network.train()
    pixels = torch.rand(2, 3, 224, 224, device="cuda")
    optim.zero_grad(set_to_none=True)
    loss = (network(pixels) - 0.02).square().mean()
    loss.backward()
    optim.step()


before = {key: value.clone() for key, value in model.features.state_dict().items()}
step(model, optimizer)
saved = checkpoint_bytes(
    make_checkpoint(
        model,
        optimizer,
        None,
        generator,
        binding={"fixture": True},
        epoch=1,
        global_step=1,
        history=[],
        best_state={},
    )
)
step(model, optimizer)
expected = {key: value.clone() for key, value in model.state_dict().items()}
expected_optimizer = optimizer.state_dict()
resumed = HybridNetwork(None).cuda()
resumed_optimizer = torch.optim.AdamW(resumed.head.parameters(), lr=0.001)
restore_checkpoint(
    torch.load(io.BytesIO(saved), weights_only=True, map_location="cpu"),
    resumed,
    resumed_optimizer,
    None,
    generator,
)
step(resumed, resumed_optimizer)
assert all(torch.equal(expected[key], value) for key, value in resumed.state_dict().items())
assert all(torch.equal(before[key], value) for key, value in resumed.features.state_dict().items())
for key, state in expected_optimizer["state"].items():
    assert all(
        torch.equal(value, resumed_optimizer.state_dict()["state"][key][name])
        for name, value in state.items()
    )
print(
    json.dumps(
        {
            "fixture": "synthetic-only",
            "cuda": torch.version.cuda,
            "torch": str(torch.__version__),
            "model_exact": True,
            "optimizer_exact": True,
            "batchnorm_and_backbone_unchanged": True,
            "operator_images": 0,
            "registered_runs": 0,
        }
    )
)
