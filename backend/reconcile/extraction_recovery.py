"""Keep original readings when optional vision proposes additional evidence."""
from copy import deepcopy
from decimal import Decimal,InvalidOperation
import re


def equivalent(field,a,b):
    if field in ['grand_total','subtotal','tax_total']:
        try:return Decimal(a)==Decimal(b)
        except (InvalidOperation,TypeError):return False
    # Preserve leading identifier zeros and meaningful suffixes.
    return re.sub(r'\s+','',a).casefold()==re.sub(r'\s+','',b).casefold()


def combine_header_readings(local,vision):
    """No business decision. A proposed value never repairs an original reading.

    A disagreement stays ambiguous. A missing OCR value may have a vision
    proposal, explicitly unverified and queued for further checks/review.
    Original row collections are retained separately, never spliced by gold fit.
    """
    result=deepcopy(local)
    result['recovery_source']='vision_proposal'
    result['original_extraction']=deepcopy(local)
    result['vision_proposal']=deepcopy(vision)
    for name,proposed in vision['header'].items():
        original=local['header'].get(name,{'value':None,'status':'missing','evidence':[],'alternatives':[]})
        merged=deepcopy(original)
        merged['readings']=[deepcopy(original),deepcopy(proposed)]
        if original['status']=='found' and proposed['status']=='found':
            if not equivalent(name,original['value'],proposed['value']):
                merged.update(value=None,status='ambiguous',alternatives=list(dict.fromkeys([original['value'],proposed['value']])))
        elif original['status']=='missing' and proposed['status']=='found':
            merged=deepcopy(proposed)
            merged['readings']=[deepcopy(original),deepcopy(proposed)]
            merged['requires_source_verification']=True
        # An absent proposal cannot erase an original valid reading or ambiguity.
        result['header'][name]=merged
    result['warnings']=sorted(set(result.get('warnings',[])+['recovery_readings_preserved','vision_proposals_not_auto_verified']))
    return result
