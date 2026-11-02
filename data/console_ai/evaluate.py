import json,time,concurrent.futures
from pathlib import Path
import httpx
from app.api.ai_assistant import rule_triage, TriageRequest
ROOT=Path(__file__).resolve().parent
rows=json.loads((ROOT/'samples.json').read_text(encoding='utf-8'))
def run(row):
 start=time.monotonic();out={"id":row['id'],"source_category":row['source_category'],"proposed_category":row['proposed_category'],"review_status":"PENDING"}
 try:
  r=httpx.post('http://127.0.0.1:8765/ai/triage',json={'issue_text':row['text']},timeout=45, trust_env=False);r.raise_for_status();d=r.json();out.update(prediction=d['category'],suggestion_source=d.get('suggestion_source'),method=d['method'],rationale=d['rationale'])
 except Exception as e:
  out['error_type']=type(e).__name__
  if isinstance(e,httpx.HTTPStatusError):out['http_status']=e.response.status_code
 out['baseline_category']=rule_triage(TriageRequest(issue_text=row['text']))['category']
 out['seconds']=round(time.monotonic()-start,3);return out
# Preserve previous run as evidence rather than overwrite it.
for name in ('predictions.json','evaluation_summary.json'):
 old=ROOT/name
 archive=ROOT/('previous_'+name)
 if old.exists() and not archive.exists(): archive.write_bytes(old.read_bytes())
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for r in pool.map(run,rows):
  results.append(r);(ROOT/'predictions.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(str(len(results))+'/'+str(len(rows)),flush=True)
eligible=[r for r in results if r['proposed_category'] is not None];model=[r for r in results if r.get('suggestion_source')=='deepseek']
summary={'total':len(results),'deepseek_returns':len(model),'rule_fallbacks':sum(r.get('suggestion_source')=='rules' for r in results),'endpoint_failures':sum('error_type' in r for r in results),'eligible_for_provisional_label_comparison':len(eligible),'provisional_matches':sum(r.get('prediction')==r['proposed_category'] for r in eligible),'warning':'Source-label mapping is unreviewed, NOT project ground truth or accuracy. Two Security cases excluded. No priority accuracy computed.','baseline_provisional_matches':sum(r['baseline_category']==r['proposed_category'] for r in eligible),'seconds_total_sum':round(sum(r['seconds'] for r in results),3)}
(ROOT/'evaluation_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
