import yaml
from pathlib import Path
from harnesses.fixed.scorer import score_fixed_accuracy

spec = yaml.safe_load(Path("tasks/simple_fitting/1-p_to_z.yaml").read_text())

# 模拟 white agent 回答（正确答案）
white_text = '{"z_scores":[1.644853626951,2.326347874041,5.0]}'

res = score_fixed_accuracy(spec=spec, white_text=white_text)
print(res.score, res.correct, res.total)
print(res.per_item)