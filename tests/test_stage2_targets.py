import unittest
from scripts.run_e5_stage2 import target
class Stage2TargetTests(unittest.TestCase):
 def row(self,labels): return {'labels':labels,'kind':'dangerous'}
 def test_direct_otp(self): self.assertTrue(target(self.row(['ACTUAL_REQUEST','DIRECTED_AT_USER','CREDENTIAL_DISCLOSURE'])))
 def test_protective_otp(self): self.assertFalse(target(self.row(['NEGATION','PROTECTIVE_ADVICE'])))
 def test_money(self): self.assertTrue(target(self.row(['ACTUAL_REQUEST','DIRECTED_AT_USER','MONEY_OR_ASSET_MOVEMENT'])))
 def test_ordinary_payment(self): self.assertFalse(target(self.row([])))
 def test_remote(self): self.assertTrue(target(self.row(['ACTUAL_REQUEST','DIRECTED_AT_USER','REMOTE_DEVICE_ACCESS'])))
 def test_legitimate(self): self.assertFalse(target(self.row(['PROTECTIVE_ADVICE'])))
 def test_manipulation_only(self): self.assertFalse(target(self.row(['ACTUAL_REQUEST','DIRECTED_AT_USER','URGENCY_OR_TIME_PRESSURE'])))
 def test_quotation(self): self.assertFalse(target(self.row(['ACTUAL_REQUEST','DIRECTED_AT_USER','MONEY_OR_ASSET_MOVEMENT','QUOTATION'])))
 def test_hypothetical(self): self.assertFalse(target(self.row(['ACTUAL_REQUEST','DIRECTED_AT_USER','MONEY_OR_ASSET_MOVEMENT','HYPOTHETICAL'])))
