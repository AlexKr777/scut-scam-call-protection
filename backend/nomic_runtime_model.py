"""Frozen Nomic V1 production model shape; no training workflow imports."""
from scripts.championship_backbones import ScutModel


class NonlinearScutModel(ScutModel):
    def __init__(self, adapter, semantic_labels):
        import torch
        super().__init__(adapter, semantic_labels)
        hidden = adapter.hidden_size
        self.trunk = torch.nn.Sequential(torch.nn.LayerNorm(hidden), torch.nn.Linear(hidden, hidden), torch.nn.GELU(), torch.nn.Dropout(.1))
        self.semantic = torch.nn.Linear(hidden, semantic_labels)
        self.kind = torch.nn.Linear(hidden, 3)
        self.action = torch.nn.Linear(hidden, 1)

    def forward(self, batch):
        representation = self.trunk(self.adapter.encode(batch))
        return self.semantic(representation), self.kind(representation), self.action(representation)
