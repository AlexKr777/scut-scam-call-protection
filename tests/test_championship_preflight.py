import tempfile
import unittest
from pathlib import Path
from scripts.championship_preflight import build_protocol, write_protocol, sha256_file

class PreflightTests(unittest.TestCase):
 def test_protocol_enumerates_24_screening_fits(self):
  protocol=build_protocol({x:{"revision":"a"} for x in ("e5_base","xlmr_base","gte_mlm_base","nomic_v2_moe")},{})
  self.assertEqual(len(protocol["phase1_fits"]),24)
 def test_protocol_hash_immutable_after_write(self):
  with tempfile.TemporaryDirectory() as d:
   p,h=write_protocol(Path(d),{"x":1}); self.assertEqual(sha256_file(p),h)
if __name__=='__main__': unittest.main()
