"""Compatibility re-export: the network moved to the neutral training core (TASK-0996)."""

from ..training_core.neural_grid_network import (
    MEAN as MEAN,
)
from ..training_core.neural_grid_network import (
    STD as STD,
)
from ..training_core.neural_grid_network import (
    BoardExport as BoardExport,
)
from ..training_core.neural_grid_network import (
    BoardNetwork as BoardNetwork,
)
from ..training_core.neural_grid_network import (
    FeaturePyramid as FeaturePyramid,
)
from ..training_core.neural_grid_network import (
    NeuralGridNetwork as NeuralGridNetwork,
)
from ..training_core.neural_grid_network import (
    ScreenExport as ScreenExport,
)
from ..training_core.neural_grid_network import (
    ScreenNetwork as ScreenNetwork,
)
from ..training_core.neural_grid_network import (
    focal_loss as focal_loss,
)
from ..training_core.neural_grid_network import (
    node_heatmap_loss as node_heatmap_loss,
)
from ..training_core.neural_grid_network import (
    offset_loss as offset_loss,
)
from ..training_core.neural_grid_network import (
    parameter_count as parameter_count,
)
from ..training_core.neural_grid_network import (
    soft_argmax as soft_argmax,
)
