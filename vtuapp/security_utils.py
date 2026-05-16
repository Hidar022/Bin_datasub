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
    Verify Gafiapay webhook signature using explicit field concatenation
    to match the gateway's internal cryptographic layout.
    """
    if not signature or not timestamp:
        logger.warning("❌ Missing signature or timestamp for Gafiapay verification")
        return False

    secret_key = settings.GAFIAPAY_SECRET_KEY.encode('utf-8')
    timestamp_str = str(timestamp)
    
    try:
        # Decode bytes if necessary
        if isinstance(payload, bytes):
            payload_str = payload.decode('utf-8')
        else:
            payload_str = str(payload)
            
        payload_dict = json.loads(payload_str)
        
        # Safely drill down to the inner transaction dictionary block
        transaction_data = payload_dict.get('data', {}).get('transaction', {})
        
        # Pull core verification properties explicitly
        tx_id = str(transaction_data.get('id', ''))
        amount = str(transaction_data.get('amount', ''))
        currency = str(transaction_data.get('currency', ''))
        order_no = str(transaction_data.get('orderNo', ''))
        
        # Fallback to general event if nested layout isn't present
        event_name = str(payload_dict.get('event', ''))

    except Exception as e:
        logger.error(f"❌ Webhook payload dictionary parsing failure: {e}")
        return False

    # Create various string combinations that match Gafiapay signature layouts
    attempts = [
        # Format A: Explicit property chain (Standard gateway design)
        ("explicit_field_chain", f"{tx_id}{amount}{currency}{order_no}{timestamp_str}"),
        
        # Format B: Normalized compact whole body (Our previous method)
        ("compact_body_sorted", f"{json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)}{timestamp_str}"),
        ("compact_body_unsorted", f"{json.dumps(payload_dict, separators=(',', ':'))}{timestamp_str}"),
        
        # Format C: Simple concatenation of core data blocks
        ("tx_id+timestamp", f"{tx_id}{timestamp_str}"),
        ("order_no+timestamp", f"{order_no}{timestamp_str}"),
        ("event+timestamp", f"{event_name}{timestamp_str}")
    ]
    
    # Run the comparison loop
    for format_name, message_string in attempts:
        # Skip attempt if essential tracking variables are blank
        if "explicit" in format_name and not (tx_id and amount):
            continue
            
        try:
            computed_sig = hmac.new(
                secret_key,
                message_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if hmac.compare_digest(computed_sig, signature):
                logger.info(f"✅ Gafiapay signature verified successfully using {format_name}!")
                return True
        except Exception as e:
            logger.warning(f"Error checking verification model {format_name}: {e}")
            continue

    logger.warning("❌ INVALID Gafiapay signature verification failure across all structural layout checks.")
    return False


def check_webhook_timestamp(timestamp_str, max_age_seconds=600):
    """
    Verify webhook timestamp is recent (prevent replay attacks)
    Handles milliseconds strings gracefully.
    """
    from datetime import datetime
    try:
        # Convert milliseconds from gateway to python timestamp object
        webhook_time = datetime.fromtimestamp(int(timestamp_str) / 1000)
        
        # Calculate difference against native local server time
        current_time = datetime.now() 
        age = (current_time - webhook_time).total_seconds()
        
        # Using abs() handles slight clock drifts between your server and Gafiapay
        if abs(age) > max_age_seconds:
            return False
        
        return True
    except Exception as e:
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
