import unittest

import torch
from torch import nn

from scripts.championship_backbones import BackboneAdapter, ScutModel, TechnicalExclusion


class FakeOutput:
    def __init__(self, tensor):
        self.last_hidden_state = tensor


class FakeEncoder(nn.Module):
    def __init__(self, blocks=12, hidden=4):
        super().__init__()
        self.encoder = nn.Module()
        self.encoder.layer = nn.ModuleList([nn.Linear(hidden, hidden) for _ in range(blocks)])
        self.config = type("Config", (), {"hidden_size": hidden})()

    def forward(self, input_ids, attention_mask=None, **_kwargs):
        tensor = input_ids.float().unsqueeze(-1).repeat(1, 1, self.config.hidden_size)
        for block in self.encoder.layer:
            tensor = block(tensor)
        return FakeOutput(tensor)


class ChampionshipBackboneTests(unittest.TestCase):
    def adapter(self, pooling="mean", blocks=12):
        return BackboneAdapter("fake", "commit", None, FakeEncoder(blocks=blocks), pooling=pooling)

    def test_top_four_unfreezes_exact_final_blocks(self):
        proof = self.adapter().configure_trainable_layers(4)
        self.assertEqual(proof.block_ids, ["8", "9", "10", "11"])
        self.assertGreater(proof.encoder_trainable_parameters, 0)

    def test_rejects_depth_larger_than_architecture(self):
        with self.assertRaises(TechnicalExclusion):
            self.adapter(blocks=2).configure_trainable_layers(4)

    def test_e5_mean_pooling_respects_attention_mask(self):
        adapter = self.adapter("mean")
        hidden = torch.tensor([[[1.0, 1.0], [3.0, 3.0]]])
        self.assertTrue(torch.equal(adapter.pool(hidden, torch.tensor([[1, 0]])), torch.tensor([[1.0, 1.0]])))

    def test_first_token_pooling_uses_first_representation(self):
        adapter = self.adapter("first_token")
        hidden = torch.tensor([[[1.0, 1.0], [3.0, 3.0]]])
        self.assertTrue(torch.equal(adapter.pool(hidden, torch.tensor([[0, 1]])), torch.tensor([[1.0, 1.0]])))

    def test_scut_model_returns_all_head_shapes(self):
        model = ScutModel(self.adapter(), semantic_labels=27)
        semantic, kind, action = model({"input_ids": torch.ones(2, 3, dtype=torch.long), "attention_mask": torch.ones(2, 3)})
        self.assertEqual(tuple(semantic.shape), (2, 27))
        self.assertEqual(tuple(kind.shape), (2, 3))
        self.assertEqual(tuple(action.shape), (2, 1))

    def test_scut_model_registers_encoder_for_device_transfer(self):
        adapter = self.adapter()
        model = ScutModel(adapter, semantic_labels=1)
        self.assertTrue(any(name.startswith("encoder.") for name, _ in model.named_parameters()))


if __name__ == "__main__":
    unittest.main()
