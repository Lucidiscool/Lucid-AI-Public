"""Generate local model answers to existing reserved review prompts."""
import ast
import json
import time
import sys
from local_chat import Backend, ROOT, SYSTEM

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
backend = Backend()
backend.start()
cases = json.loads((ROOT / 'examples/dialogue_holdout.json').read_text())
tree = ast.parse((ROOT / 'evaluate.py').read_text(encoding='utf-8'))
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CASES' for t in node.targets):
        for category, prompt, rubric in ast.literal_eval(node.value):
            cases.append(dict(id='general_' + category, messages=[dict(role='user', content=prompt)], rubric=rubric))
results = []
try:
    for case in cases:
        start = time.monotonic()
        answer = backend.answer([dict(role='system', content=SYSTEM)] + case['messages'],
                                max_tokens=256, temperature=0, display=False)[-1]['content']
        results.append(dict(**case, answer=answer, seconds=round(time.monotonic()-start, 2)))
        print(case['id'] + ': ' + answer, flush=True)
        (ROOT / 'runs/open-model-review.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
finally:
    backend.client.close()
