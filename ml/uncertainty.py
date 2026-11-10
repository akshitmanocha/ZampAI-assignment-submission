"""Selective matching diagnostics. Pair labels are not invoice-bucket labels.

Threshold selection uses validation only. No 100% future-risk guarantee is
possible from a finite sample. Group bounds require independent/exchangeable
future groups; synthetic family results cannot certify production.
"""
import math
import numpy as np
from scipy.stats import beta


def upper_error_bound(errors,n,confidence=.95):
    if not 0<confidence<1 or not 0<=errors<=n:
        raise ValueError('Invalid confidence or counts')
    if n==0 or errors==n:return 1.0
    return float(beta.ppf(confidence,errors+1,n-errors))


def choose_match_threshold(validation):
    """Maximize observed automatic matches subject to zero validation errors.

    No low-score invoice rejection: uncertain/non-matching pairs stay unresolved.
    Selection is a development objective, not a statistical certificate.
    """
    candidates=sorted({r['score'] for r in validation})
    choices=[]
    for t in candidates:
        accepted=[r for r in validation if r['score']>=t]
        if accepted and all(r['label']==1 for r in accepted):choices.append((len(accepted),t))
    return max(choices,key=lambda x:(x[0],x[1]))[1] if choices else math.inf


def evaluate(rows,threshold,confidence=.95):
    accepted=[r for r in rows if r['score']>=threshold]
    errors=sum(r['label']!=1 for r in accepted)
    groups={r['family'] for r in accepted}
    group_errors=sum(any(r['label']!=1 for r in accepted if r['family']==g) for g in groups)
    return {'pairs':len(rows),'automatically_matched_pairs':len(accepted),'review_pairs':len(rows)-len(accepted),'automatic_coverage':len(accepted)/len(rows) if rows else 0,'wrong_automatic_matches':errors,'observed_match_precision':1-errors/len(accepted) if accepted else None,'accepted_families':len(groups),'families_with_any_wrong_automatic_match':group_errors,'family_error_upper_bound_95':upper_error_bound(group_errors,len(groups),confidence),'bound_scope':'probability of any wrong automatic match within a future independent comparable family; NOT invoice error probability','strict_zero_risk_certified':False}
