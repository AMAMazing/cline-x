import secrets
from functools import wraps
from flask import request, abort
from modules.config_utils import read_config

API_KEY = secrets.token_urlsafe(32)

def require_api_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        config = read_config()
        current_auth_required = str(config.get('auth_required', 'False')).lower() == 'true'
        if not current_auth_required:
            return func(*args, **kwargs)
            
        if request.headers.get('X-API-Key') == API_KEY or request.headers.get('Authorization', '').replace('Bearer ', '') == API_KEY:
            return func(*args, **kwargs)
            
        if request.args.get('api_key') == API_KEY:
             return func(*args, **kwargs)
             
        abort(401, description="Invalid or missing API key")
    return wrapper