"""Small deterministic threshold calibration over held-out scenario groups."""
from __future__ import annotations

def threshold_from_validation(rows: list[tuple[float,bool]]) -> float:
    if not rows: raise ValueError("validation rows required")
    candidates=sorted({score for score,_ in rows}); best=(float("-inf"),candidates[-1])
    for threshold in candidates:
        tp=sum(score>=threshold and truth for score,truth in rows); fp=sum(score>=threshold and not truth for score,truth in rows); fn=sum(score<threshold and truth for score,truth in rows)
        score=2*tp/max(1,2*tp+fp+fn)
        if score>best[0]: best=(score,threshold)
    return best[1]
