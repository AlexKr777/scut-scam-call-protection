import unittest

from scripts.tail_aware_encoder import pack_turns


class FakeTokenizer:
    def __call__(self, text, add_special_tokens=True, **_kwargs):
        return {"input_ids": list(range(len(text.split()) + (2 if add_special_tokens else 0)))}


class TailAwareEncoderTests(unittest.TestCase):
    def test_packing_is_deterministic_and_keeps_speaker_tags(self):
        turns = [("CALLER", "hello"), ("USER", "please help")]
        self.assertEqual(pack_turns(turns, FakeTokenizer(), 32), pack_turns(turns, FakeTokenizer(), 32))
        self.assertIn("[CALLER] hello", pack_turns(turns, FakeTokenizer(), 32))
        self.assertIn("[USER] please help", pack_turns(turns, FakeTokenizer(), 32))

    def test_pack_retains_final_request_when_opening_turn_is_oversized(self):
        packed = pack_turns([("CALLER", "x " * 1000), ("CALLER", "read the OTP")], FakeTokenizer(), 384)
        self.assertIn("read the OTP", packed)
        self.assertIn("[CONTEXT_OMITTED]", packed)
        self.assertLessEqual(len(FakeTokenizer()(packed)["input_ids"]), 384)

    def test_prefix_participates_in_budget(self):
        packed = pack_turns([("CALLER", "one"), ("USER", "two")], FakeTokenizer(), 32, prefix="query: ")
        self.assertTrue(packed.startswith("query: "))


if __name__ == "__main__":
    unittest.main()
