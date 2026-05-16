"""
Security utilities for Bin Datasub
- Webhook signature verification
- Rate limiting helpers
- Input sanitization
"""


import json
import hmac
import hashlib
import logging
from django.conf import settings
from datetime import datetime, timedelta
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ===================== WEBHOOK VERIFICATION =====================

def verify_paystack_signature(payload, signature):
    """
    Verify Paystack webhook signature
    
    Args:
        payload: Raw request body
        signature: X-Paystack-Signature header value
    
    Returns:
        bool: True if signature is valid
    """
    hash_object = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode('utf-8'),
        payload,
        hashlib.sha512
    )
    computed_signature = hash_object.hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(computed_signature, signature)
    
    if not is_valid:
        logger.warning(f"❌ INVALID Paystack signature detected - possible attack")
    
    return is_valid



def verify_gafiapay_signature(payload, signature, timestamp):
    """
    Verify Gafiapay signature by calculating the HMAC SHA256 of the 
    received payload with the 'signature' key removed.
    """
    if not signature:
        logger.warning("❌ Missing signature string for verification")
        return False

    try:
        # 1. Safely decode raw payload to text string
        if isinstance(payload, bytes):
            payload_str = payload.decode('utf-8')
        else:
            payload_str = str(payload)

        # 2. Parse into Python dictionary
        payload_dict = json.loads(payload_str)
        
        # 3. POP out the signature key (this matches the exact payload state before signing)
        payload_dict.pop('signature', None)
        
        # 4. Convert back to exact compact JSON structure matching gateway standards
        # Gafiapay builds signatures using standard unsorted compact keys
        cleaned_payload_str = json.dumps(payload_dict, separators=(',', ':'))

    except Exception as e:
        logger.error(f"❌ Failed to process payload data text structure: {e}")
        return False

    # 5. Fetch secret key securely
    secret_key = settings.GAFIAPAY_SECRET_KEY.encode('utf-8')

    # 6. Check the raw payload variation and explicit property formats
    attempts = [
        ("clean_body_raw", cleaned_payload_str),
        ("clean_body_plus_timestamp", f"{cleaned_payload_str}{timestamp}"),
    ]

    for format_name, message_string in attempts:
        computed_sig = hmac.new(
            secret_key,
            message_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(computed_sig, signature):
            logger.info(f"✅ Gafiapay signature verified successfully using {format_name}!")
            return True

    logger.warning("❌ INVALID Gafiapay signature verification failure after exact body processing.")
    return False

def check_webhook_timestamp(timestamp_str, max_age_seconds=600):
    """
    Verify webhook timestamp is recent (prevent replay attacks)
    """
    from datetime import datetime
    try:
        webhook_time = datetime.fromtimestamp(int(timestamp_str) / 1000)
        current_time = datetime.now() 
        age = (current_time - webhook_time).total_seconds()
        
        if abs(age) > max_age_seconds:
            return False
        return True
    except Exception:
        return False
# ===================== RATE LIMITING =====================

def is_rate_limited(key, limit=5, window=60):
    """
    Simple rate limiting using Django cache
    
    Args:
        key: Unique identifier (e.g., 'login_user_id_123')
        limit: Max requests allowed in window
        window: Time window in seconds
    
    Returns:
        bool: True if rate limited, False if allowed
    """
    current_count = cache.get(key, 0)
    
    if current_count >= limit:
        logger.warning(f"🚫 Rate limit exceeded for {key}")
        return True
    
    cache.set(key, current_count + 1, window)
    return False


def get_rate_limit_key(request, action):
    """
    Generate rate limit key from request
    
    Args:
        request: Django request object
        action: Action name (e.g., 'login', 'buy_airtime')
    
    Returns:
        str: Rate limit key
    """
    user_id = request.user.id if request.user.is_authenticated else request.META.get('REMOTE_ADDR')
    return f"ratelimit_{action}_{user_id}"


def account_lockout_key(username):
    """Generate account lockout cache key"""
    return f"lockout_{username}"


def check_account_lockout(username, max_attempts=5, lockout_minutes=30):
    """
    Check if account is locked out
    
    Args:
        username: User's username
        max_attempts: Max failed attempts before lockout
        lockout_minutes: Minutes to lock account
    
    Returns:
        dict: {'locked': bool, 'remaining_minutes': int}
    """
    key = account_lockout_key(username)
    attempts = cache.get(key, 0)
    
    if attempts >= max_attempts:
        ttl = cache.ttl(key)
        remaining_minutes = (ttl / 60) if ttl > 0 else 0
        return {
            'locked': True,
            'remaining_minutes': remaining_minutes
        }
    
    return {'locked': False, 'remaining_minutes': 0}


def record_failed_login(username, max_attempts=5, lockout_minutes=30):
    """
    Record failed login attempt
    
    Args:
        username: User's username
        max_attempts: Max failed attempts before lockout
        lockout_minutes: Minutes to lock account
    """
    key = account_lockout_key(username)
    attempts = cache.get(key, 0)
    attempts += 1
    
    if attempts >= max_attempts:
        logger.warning(f"🔒 Account locked after {attempts} failed attempts: {username}")
        cache.set(key, attempts, lockout_minutes * 60)
    else:
        cache.set(key, attempts, lockout_minutes * 60)


def reset_failed_login(username):
    """Clear failed login counter on successful login"""
    key = account_lockout_key(username)
    cache.delete(key)


# ===================== LOGGING =====================

def log_security_event(event_type, user=None, details=None, severity='INFO'):
    """
    Log security events
    
    Args:
        event_type: Type of event (e.g., 'failed_login', 'suspicious_transaction')
        user: User object (optional)
        details: Additional details (optional)
        severity: Log level ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
    """
    message = f"[{event_type}]"
    if user:
        message += f" User: {user.username}"
    if details:
        message += f" Details: {details}"
    
    if severity == 'INFO':
        logger.info(message)
    elif severity == 'WARNING':
        logger.warning(message)
    elif severity == 'ERROR':
        logger.error(message)
    elif severity == 'CRITICAL':
        logger.critical(message)
