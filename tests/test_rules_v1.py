import unittest
from scripts.rules_v1 import analyze
class RulesV1Tests(unittest.TestCase):
 def test_caller_directed_multilingual_actions_are_high_risk(self):
  x=analyze([('CALLER','Sunt de la bancă. Spuneți-mi codul OTP acum.'),('USER','что?'),('CALLER','Установите AnyDesk и скажите код.')]);self.assertTrue(x['actual_request']);self.assertTrue(x['credentials_request']);self.assertTrue(x['remote_access_request']);self.assertEqual(set(x['languages_seen']),{'ro','ru','en'})
 def test_protective_quote_hypothetical_and_user_repeat_do_not_become_request(self):
  for turns in [[('CALLER','Never read the code to a caller.')],[('USER','Вы хотите, чтобы я назвал код?')],[('CALLER','If I asked for the code, would that be safe?')]]: self.assertFalse(analyze(turns)['actual_request'])
 def test_context_memory_combines_identity_pressure_and_later_action(self):
  x=analyze([('CALLER','банк'),('CALLER','срочно, не кладите трубку'),('CALLER','назовите код')]);self.assertTrue(x['actual_request']);self.assertTrue(x['caller_claimed_identity'])
 def test_deterministic(self):
  t=[('CALLER','Nu vă cer parola. Spuneți-mi doar cifrele primite.')];self.assertEqual(analyze(t),analyze(t))
