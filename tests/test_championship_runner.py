import tempfile,unittest
from pathlib import Path
from scripts.run_brain_championship import FrozenSelection,can_resume,persist_fit,persist_fit_result,run_confirmatory_validation_once,run_fit,select_finalists
from scripts.championship_backbones import BackboneAdapter,ScutModel
import torch
from torch import nn
class Tok:
 def __call__(self,texts,**kw):
  if isinstance(texts,str):texts=[texts]
  return {'input_ids':torch.ones(len(texts),4,dtype=torch.long),'attention_mask':torch.ones(len(texts),4,dtype=torch.long)}
class Enc(nn.Module):
 def __init__(self,blocks=6):
  super().__init__();self.encoder=nn.Module();self.encoder.layer=nn.ModuleList([nn.Linear(3,3) for _ in range(blocks)]);self.config=type('C',(),{'hidden_size':3})()
 def forward(self,input_ids,**kw):
  x=torch.ones(input_ids.shape[0],input_ids.shape[1],3)
  for b in self.encoder.layer:x=b(x)
  return type('O',(),{'last_hidden_state':x})()
class RunnerTests(unittest.TestCase):
 def test_resume_requires_exact_protocol_and_complete_oof(self):
  with tempfile.TemporaryDirectory() as d:
   fit={"fit_id":"x","fold":0}; protocol={"_sha256":"a"}; (Path(d)/"x.npz").write_bytes(b"evidence"); path=persist_fit(Path(d),fit,protocol,{"oof_npz":"x.npz"})
   self.assertFalse(can_resume(fit,protocol,path)); self.assertFalse(can_resume(fit,{"_sha256":"b"},path))
 def test_validation_cannot_mutate_frozen_selection(self):
  f=FrozenSelection("e5_base",4,29,{"action":.6}); run_confirmatory_validation_once(lambda:{"passed":True},f); self.assertEqual(f.seed,29)
 def test_fit_record_requires_npz_evidence_reference(self):
  with tempfile.TemporaryDirectory() as d:
   fit={"fit_id":"x","fold":0}; protocol={"_sha256":"a"}; path=persist_fit(Path(d),fit,protocol,{})
   self.assertFalse(can_resume(fit,protocol,path))
 def test_tiny_fit_trains_and_persists_real_oof(self):
  rows=[{'id':f'r{i}','base_scenario_id':f'g{i}','turns':[('CALLER','x')],'labels':['ACTUAL_REQUEST','DIRECTED_AT_USER','CREDENTIAL_DISCLOSURE'] if i%2 else [],'kind':'dangerous' if i%2 else 'legitimate'} for i in range(6)]
  fit={'fit_id':'tiny','candidate':'e5_base','depth':2,'fold':0,'seed':17}; protocol={'_sha256':'x','_test_allow_cpu':True,'candidates':{'e5_base':{'revision':'local'}},'constants':{'encoder_lr':{'top_2':1e-3,'top_4':1e-3}}}; a=BackboneAdapter('fake','local',Tok(),Enc(),pooling='mean'); r=run_fit(fit,protocol,rows[:4],rows[4:],['CREDENTIAL_DISCLOSURE'],a,ScutModel(a,1),device='cpu',micro_batch=2)
  with tempfile.TemporaryDirectory() as d:
   p=persist_fit_result(Path(d),fit,protocol,rows[:4],rows[4:],r); self.assertTrue(can_resume(fit,protocol,p));self.assertTrue(r['changed']);self.assertTrue(r['warmup_encoder_unchanged']);self.assertEqual(r['block_changed'],[False,False,False,False,True,True]);self.assertGreater(r['gradient'],0);self.assertEqual(len(r['arrays']['record_ids']),2)
 def test_tiny_depth_four_updates_only_last_four_blocks(self):
  rows=[{'id':f'r{i}','base_scenario_id':f'g{i}','turns':[('CALLER','x')],'labels':['ACTUAL_REQUEST','DIRECTED_AT_USER','CREDENTIAL_DISCLOSURE'] if i%2 else [],'kind':'dangerous' if i%2 else 'legitimate'} for i in range(6)]
  fit={'fit_id':'tiny4','candidate':'e5_base','depth':4,'fold':0,'seed':17}; protocol={'_sha256':'x','_test_allow_cpu':True,'candidates':{'e5_base':{'revision':'local'}},'constants':{'encoder_lr':{'top_2':1e-3,'top_4':1e-3}}}; a=BackboneAdapter('fake','local',Tok(),Enc(6),pooling='mean');r=run_fit(fit,protocol,rows[:4],rows[4:],['CREDENTIAL_DISCLOSURE'],a,ScutModel(a,1),device='cpu',micro_batch=2)
  self.assertTrue(r['warmup_encoder_unchanged']);self.assertEqual(r['block_changed'],[False,False,True,True,True,True]);self.assertGreater(r['gradient'],0)
 def test_resume_rejects_corrupt_npz(self):
  with tempfile.TemporaryDirectory() as d:
   fit={'fit_id':'x','candidate':'e5_base','depth':2,'fold':0,'seed':17}; protocol={'_sha256':'a','candidates':{'e5_base':{'revision':'r'}}}; p=Path(d)/'x.npz';p.write_bytes(b'bad'); path=persist_fit(Path(d),fit,protocol,{'candidate_id':'e5_base','revision':'r','depth':2,'seed':17,'oof_npz':'x.npz','npz_sha256':'x','oof_record_ids':['a'],'oof_group_ids':['g']});self.assertFalse(can_resume(fit,protocol,path))
 def test_selection_does_not_promote_an_unqualified_candidate(self):
  self.assertEqual(select_finalists([{'id':'unsafe','qualification':{'qualified':False}}]),[])
if __name__=='__main__':unittest.main()
