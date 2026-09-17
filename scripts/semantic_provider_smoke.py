"""Real selected-provider semantic-schema health check; never prints credentials."""
import sys
import time
from pathlib import Path

# Support the documented `python scripts/…` invocation from the repository.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.semantic_risk import ProviderError, provider_from_environment

provider=provider_from_environment()
if not provider: raise SystemExit("UNAVAILABLE: set SCUT_AI_PROVIDER, SCUT_AI_BASE_URL, SCUT_AI_MODEL, and SCUT_AI_API_KEY")
payload={"call_id":"smoke","semantic_revision":1,"accumulated_state":{},"new_finalized_utterances":[{"utterance_id":"u1","speaker":"CALLER","text":"I am from the bank; tell me the SMS code now.","stable":True}],"recent_context":[]}
started=time.perf_counter()
try:
    delta=provider.extract(payload)
except ProviderError as error:
    print({"status":"UNAVAILABLE","provider":provider.provider_name,"configuredModel":provider.model,"category":error.category,"latencyMs":round((time.perf_counter()-started)*1000,1)})
    raise SystemExit(2)
total = (time.perf_counter()-started)*1000
print({"status":"AVAILABLE","provider":provider.provider_name,"configuredModel":provider.model,"returnedModel":provider.last_response_model,"httpSuccess":True,"schemaValid":bool(delta),"requestLatencyMs":round(provider.last_request_ms or 0,1),"parseSchemaLatencyMs":round(provider.last_parse_ms or 0,1),"totalSemanticLatencyMs":round(total,1)})
