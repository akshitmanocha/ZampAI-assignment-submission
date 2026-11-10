from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code, message, status=409, details=None, retryable=False):
        self.code, self.message, self.status = code, message, status
        self.details, self.retryable = details or {}, retryable


def response(error, request_id=''):
    headers = {'WWW-Authenticate': 'Session realm="reconcile"'} if error.status == 401 else {}
    if error.status == 429:
        headers['Retry-After'] = '900'
    return JSONResponse({'error': {'code': error.code, 'message': error.message,
        'details': error.details, 'retryable': error.retryable, 'request_id': request_id}},
        status_code=error.status, headers=headers)
