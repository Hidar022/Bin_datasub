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
    Verify Gafiapay webhook signature by safely extracting normalized JSON
    to match standard payment gateway payload signature structures.
    """
    if not signature or not timestamp:
        logger.warning("❌ Missing signature or timestamp for Gafiapay verification")
        return False

    secret_key = settings.GAFIAPAY_SECRET_KEY.encode('utf-8')
    timestamp_str = str(timestamp)
    
    # Step 1: Normalize payload to an identical compressed string format
    try:
        # If payload is passed as bytes, decode it to string first
        if isinstance(payload, bytes):
            payload_str = payload.decode('utf-8')
        else:
            payload_str = str(payload)
            
        # Parse into a python dictionary
        payload_dict = json.loads(payload_str)
        
        # Strip all whitespace formatting and sort keys alphabetically to maintain strict matching
        normalized_json = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True)
        # Also prepare an unsorted version just in case their webhook engine does not sort keys
        normalized_json_unsorted = json.dumps(payload_dict, separators=(",", ":"))
        
    except Exception as e:
        logger.error(f"❌ Failed to normalize webhook payload JSON: {e}")
        return False

    # Step 2: Formulate potential message patterns 
    # (Payload + Timestamp is their standard outgoing signature pattern)
    attempts = [
        ("sorted_payload+timestamp", f"{normalized_json}{timestamp_str}"),
        ("unsorted_payload+timestamp", f"{normalized_json_unsorted}{timestamp_str}"),
        ("timestamp+sorted_payload", f"{timestamp_str}{normalized_json}"),
        ("timestamp+unsorted_payload", f"{timestamp_str}{normalized_json_unsorted}"),
    ]
    
    # Step 3: Run secure constant-time check loops across the variations
    for format_name, message_string in attempts:
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
            logger.warning(f"Error checking variation {format_name}: {e}")
            continue

    logger.warning(f"❌ INVALID Gafiapay signature verification failure.")
    return False


def check_webhook_timestamp(timestamp_str, max_age_seconds=600): # Increased to 10 mins to account for server drift
    """
    Verify webhook timestamp is recent, dealing gracefully with naive vs aware timezones
    """
    try:
        # Convert milliseconds from gateway to timestamp
        webhook_time = datetime.fromtimestamp(int(timestamp_str) / 1000)
        
        # FIX: Check naive local time difference to avoid native UTC vs local server time mismatch
        current_time = datetime.now() 
        age = (current_time - webhook_time).total_seconds()
        
        # Absolute value handles slight clock differences between your server and Gafiapay
        if abs(age) > max_age_seconds:
            logger.warning(f"❌ Webhook timestamp out of acceptable bounds. Age: {age} seconds")
            return False
        
        return True
    except Exception as e:
        logger.error(f"❌ Error validating timestamp: {e}")
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
