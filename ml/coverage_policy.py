"""Two-sided abstention for PRODUCT PAIRS, not invoice accept/reject.

A negative pair means this candidate is not the product; search other candidates
or review the invoice. It never authorizes automatic invoice rejection.
"""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class PairPolicy:
    nonmatch_max: float
    match_min: float
    target_coverage: float

    def __post_init__(self):
        if not (math.isfinite(self.nonmatch_max) and math.isfinite(self.match_min) and self.nonmatch_max < self.match_min and 0 < self.target_coverage <= 1):
            raise ValueError("Invalid finite decision bounds or coverage")

    def classify(self,score):
        if not math.isfinite(score):return 'review'
        if score<=self.nonmatch_max:return 'different_product'
        if score>=self.match_min:return 'same_product'
        return 'review'


def fit(validation,target=.9):
    if not validation or not 0<target<=1:raise ValueError('Validation rows and valid coverage required')
    if any(not math.isfinite(r['score']) or r['label'] not in (0,1) for r in validation):
        raise ValueError('Finite scores and binary labels required')
    values=sorted({r['score'] for r in validation})
    cuts=[math.nextafter(values[0],-math.inf)]+values+[math.nextafter(values[-1],math.inf)]
    best=None
    for lo in cuts:
        for hi in cuts:
            if lo>=hi:continue
            policy=PairPolicy(lo,hi,target)
            report=evaluate(validation,policy)
            if report['automation']+1e-12<target:continue
            key=(report['automatic_accuracy'], -abs(report['automation']-target), -report['wrong_same_product'], hi-lo)
            if best is None or key>best[0]:best=(key,policy)
    return best[1]


def evaluate(rows,policy):
    automatic=correct=wrong_same=wrong_different=same=different=0
    for r in rows:
        prediction=policy.classify(r['score'])
        if prediction=='review':continue
        automatic+=1
        same+=prediction=='same_product';different+=prediction=='different_product'
        truth='same_product' if r['label']==1 else 'different_product'
        correct+=prediction==truth
        wrong_same+=prediction=='same_product' and r['label']==0
        wrong_different+=prediction=='different_product' and r['label']==1
    return {'pairs':len(rows),'automatic_pairs':automatic,'review_pairs':len(rows)-automatic,'automation':automatic/len(rows) if rows else 0,'automatic_accuracy':correct/automatic if automatic else None,'same_product_precision':1-wrong_same/same if same else None,'different_product_precision':1-wrong_different/different if different else None,'wrong_same_product':wrong_same,'wrong_different_product':wrong_different}


def evaluate_at_budget(rows,policy,target=.9):
    """Offline batch diagnostic: review the lowest-margin ~10% without labels.

    Model decision boundary is fixed from validation. Labels are used only after
    selecting rows, to measure errors. This is not a production review quota:
    hard evidence failures must override it and may require more than 10% review.
    """
    if not rows or not 0<target<=1:raise ValueError('Rows and valid coverage required')
    center=(policy.nonmatch_max+policy.match_min)/2
    eligible=[(i,abs(r['score']-center)) for i,r in enumerate(rows) if math.isfinite(r['score'])]
    # Stable ties are for reproducible offline counts; online ties should share
    # the conservative threshold, so exact coverage is not promised in serving.
    selected={i for i,_ in sorted(eligible,key=lambda p:(-p[1],p[0]))[:math.ceil(target*len(rows))]}
    chosen=[]
    for i,r in enumerate(rows):
        if i in selected:chosen.append(r)
    binary=PairPolicy(math.nextafter(center,-math.inf),center,target)
    report=evaluate(chosen,binary)
    report.update({'pairs':len(rows),'automatic_pairs':len(chosen),'review_pairs':len(rows)-len(chosen),'automation':len(chosen)/len(rows),'decision_boundary':center,'selection':'highest absolute distance from validation-fixed boundary; no evaluation labels used for selection','production_quota_enabled':False})
    return report
