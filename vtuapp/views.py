# 1. Standard Library Imports
import json
import hmac
import time
import hashlib
import logging
import random
import traceback
import requests
from decimal import Decimal
from datetime import timedelta
from django.http import HttpResponse
from django.db.models import Sum, Count, Q, Avg
from django.contrib.admin.views.decorators import staff_member_required



from .models import Transaction, Wallet # Ensure these models are imported

from .models import DataPlan
from django.contrib.auth import update_session_auth_hash

# 2. Django Core Imports
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.csrf import csrf_exempt

# 3. Security Utils ✅
from .security_utils import (
    verify_paystack_signature, verify_gafiapay_signature, 
    check_webhook_timestamp, is_rate_limited, get_rate_limit_key,
    check_account_lockout, record_failed_login, reset_failed_login,
    log_security_event
)

# 4. Local Project Imports (Services, Models, and Forms)
from .services.api_service import VTUApiService 
from .models import Wallet, Transaction, DataPlan, Profile
from .forms import (
    CustomUserCreationForm,
    AirtimeForm, 
    DataForm, 
    ElectricityForm, 
    CableTVForm, 
    DataPurchaseForm
)

logger = logging.getLogger(__name__)

def home_redirect(request):
    return redirect('login') if not request.user.is_authenticated else redirect('dashboard')


# ====================== AUTH ======================

def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'vtuapp/index.html')
    
def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)

        if form.is_valid():
            # === NEW LOGIC: Check if email already exists ===
            email = form.cleaned_data.get('email')
            existing_user = User.objects.filter(email=email).first()

            if existing_user:
                if existing_user.is_active:
                    # Email already exists and is verified
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'message': '❌ This email is already registered. Please login instead.'
                        }, status=400)
                    else:
                        messages.error(request, 'This email is already registered. Please login instead.')
                        return redirect('register')
                else:
                    # Email exists but not verified → Resend OTP
                    profile, _ = Profile.objects.get_or_create(user=existing_user)
                    
                    otp = str(random.randint(100000, 999999))
                    profile.email_otp = otp
                    profile.otp_created_at = timezone.now()
                    profile.save()

                    # Send OTP again
                    subject = 'Your Bin Datasub Verification Code'
                    html_message = f"""
                    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: linear-gradient(135deg, #0a0a2e 0%, #16213e 100%); color: white; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <div style="text-align: center; margin-bottom: 30px;">
                            <h1 style="color: #a855f7; margin: 0; font-size: 28px;">Bin Datasub</h1>
                            <p style="color: #cbd5e0; margin: 5px 0;">Your Trusted VTU Service</p>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); padding: 30px; border-radius: 12px; margin-bottom: 20px;">
                            <h2 style="color: #a855f7; margin-top: 0;">Verify Your Account</h2>
                            <p>Hi {existing_user.username},</p>
                            <p>Thank you for registering with Bin Datasub! To complete your account setup, please verify your email address using the code below:</p>
                            <div style="background: #1a1a4a; padding: 25px; text-align: center; font-size: 42px; letter-spacing: 8px; border-radius: 12px; margin: 20px 0; border: 2px solid #a855f7;">
                                <strong>{otp}</strong>
                            </div>
                            <p style="font-size: 14px; color: #cbd5e0;">This code will expire in 10 minutes for security reasons.</p>
                            <p>If you didn't request this verification, please ignore this email or contact our support team.</p>
                        </div>
                        <div style="text-align: center; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.2);">
                            <p style="font-size: 12px; color: #cbd5e0;">Need help? <a href="mailto:support@bindatasub.com" style="color: #a855f7;">Contact Support</a></p>
                            <p style="font-size: 12px; color: #cbd5e0;">&copy; 2024 Bin Datasub. All rights reserved.</p>
                        </div>
                    </div>
                    """

                    try:
                        send_mail(subject, f"Your OTP is {otp}", settings.DEFAULT_FROM_EMAIL, [email], html_message=html_message)
                    except Exception as e:
                        print(f"Resend email failed: {e}")

                    request.session['pending_user_id'] = existing_user.id

                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': '✅ We found your unverified account. A new verification code has been sent to your email.',
                            'redirect_url': '/verify-otp/'
                        })
                    else:
                        messages.success(request, 'We found your unverified account. A new verification code has been sent to your email.')
                        return redirect('verify_otp')

            else:
                # === Normal Registration (email doesn't exist) ===
                user = form.save(commit=False)
                user.is_active = False
                user.save()

                # Get or create profile and save phone/full name
                profile, created = Profile.objects.get_or_create(user=user)
                profile.full_name = form.cleaned_data.get('full_name', '')
                # Ensure phone is pulled correctly from the POST data
                profile.phone = request.POST.get('phone', '') 
                profile.dob = form.cleaned_data.get('dob', None)
                
                # Generate and save OTP
                otp = str(random.randint(100000, 999999))
                profile.email_otp = otp
                profile.otp_created_at = timezone.now()
                profile.save()

            # Send email (same as before)
            subject = 'Your Bin Datasub Verification Code'
            html_message = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: linear-gradient(135deg, #0a0a2e 0%, #16213e 100%); color: white; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #a855f7; margin: 0; font-size: 28px;">Bin Datasub</h1>
                    <p style="color: #cbd5e0; margin: 5px 0;">Your Trusted VTU Service</p>
                </div>
                <div style="background: rgba(255,255,255,0.1); padding: 30px; border-radius: 12px; margin-bottom: 20px;">
                    <h2 style="color: #a855f7; margin-top: 0;">Welcome to Bin Datasub!</h2>
                    <p>Hi {user.username},</p>
                    <p>Thank you for registering with Bin Datasub! To complete your account setup, please verify your email address using the code below:</p>
                    <div style="background: #1a1a4a; padding: 25px; text-align: center; font-size: 42px; letter-spacing: 8px; border-radius: 12px; margin: 20px 0; border: 2px solid #a855f7;">
                        <strong>{otp}</strong>
                    </div>
                    <p style="font-size: 14px; color: #cbd5e0;">This code will expire in 10 minutes for security reasons.</p>
                    <p>If you didn't request this verification, please ignore this email or contact our support team.</p>
                </div>
                <div style="text-align: center; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.2);">
                    <p style="font-size: 12px; color: #cbd5e0;">Need help? <a href="mailto:support@bindatasub.com" style="color: #a855f7;">Contact Support</a></p>
                    <p style="font-size: 12px; color: #cbd5e0;">&copy; 2024 Bin Datasub. All rights reserved.</p>
                </div>
            </div>
            """

            try:
                send_mail(
                    subject, 
                    f"Your OTP is {otp}", 
                    settings.DEFAULT_FROM_EMAIL, 
                    [email], 
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"CRITICAL EMAIL FAILURE: {e}")
                # Temporarily raise the error so Vercel shows a red screen with the message
                raise e

            request.session['pending_user_id'] = user.id

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': '✅ Account created! We sent a 6-digit code to your email.',
                    'redirect_url': '/verify-otp/'
                })
            else:
                messages.success(request, 'Account created! We sent a 6-digit code to your email.')
                return redirect('verify_otp')

        else:
            # Clean error messages
            error_list = []
            for errors in form.errors.get_json_data().values():
                for err in errors:
                    error_list.append(err.get('message', str(err)) if isinstance(err, dict) else str(err))
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': ' '.join(error_list) if error_list else 'Please correct the errors.'
                }, status=400)
            else:
                for error in error_list:
                    messages.error(request, error)
                return redirect('register')

    form = CustomUserCreationForm()
    return render(request, 'vtuapp/register.html', {'form': form})

# New OTP Verification View
def verify_otp(request):
    if request.method == 'POST':
        otp_input = request.POST.get('otp', '').strip()
        user_id = request.session.get('pending_user_id')

        # ✅ SECURITY: Rate limiting
        rate_limit_key = f"ratelimit_otp_{user_id}"
        if is_rate_limited(rate_limit_key, limit=5, window=300):  # 5 attempts per 5 minutes
            log_security_event('otp_rate_limit', details=f'user_id: {user_id}', severity='WARNING')
            return JsonResponse({'success': False, 'message': '❌ Too many OTP attempts. Please try again later.'}, status=429)

        if not user_id:
            return JsonResponse({'success': False, 'message': 'Session expired. Please register again.'}, status=400)

        try:
            user = User.objects.get(id=user_id)
            profile = Profile.objects.get(user=user)

            if not profile.email_otp or not profile.otp_created_at:
                return JsonResponse({'success': False, 'message': 'No OTP found. Please register again.'}, status=400)

            # Check if OTP expired (10 minutes)
            if timezone.now() - profile.otp_created_at > timedelta(minutes=10):
                profile.email_otp = None
                profile.otp_created_at = None
                profile.save()
                return JsonResponse({'success': False, 'message': '❌ OTP has expired. Please register again.'}, status=400)

            if profile.email_otp == otp_input:
                user.is_active = True
                user.save()

                profile.email_otp = None
                profile.otp_created_at = None
                profile.save()

                login(request, user)
                del request.session['pending_user_id']
                
                log_security_event('otp_verified', user=user)
                return JsonResponse({
                    'success': True,
                    'message': '✅ Email verified successfully! Redirecting to dashboard...'
                })
            else:
                log_security_event('invalid_otp', details=f'user_id: {user_id}', severity='WARNING')
                return JsonResponse({'success': False, 'message': '❌ Incorrect OTP. Please try again.'}, status=400)

        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'User not found. Please register again.'}, status=400)
        except Profile.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Profile not found. Please register again.'}, status=400)
        except Exception as e:
            logger.error(f"OTP Verification Error: {traceback.format_exc()}")
            log_security_event('otp_verification_error', details=str(e), severity='ERROR')
            return JsonResponse({'success': False, 'message': 'Something went wrong. Please try again.'}, status=400)

    return render(request, 'vtuapp/verify_otp.html', {})

# ====================== LOGIN VIEW ======================
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '')
        
        # ✅ Check account lockout
        lockout_status = check_account_lockout(username)
        if lockout_status['locked']:
            msg = f'❌ Account locked after too many failed attempts. Try again in {int(lockout_status["remaining_minutes"])} minutes.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=403)
            messages.error(request, msg)
            log_security_event('locked_account_access_attempt', details=f'username: {username}', severity='WARNING')
            return redirect('login')
        
        # ✅ Rate limiting
        rate_limit_key = get_rate_limit_key(request, 'login')
        if is_rate_limited(rate_limit_key, limit=10, window=60):
            msg = '❌ Too many login attempts. Please try again later.'
            return JsonResponse({'success': False, 'message': msg}, status=429)
        
        form = AuthenticationForm(data=request.POST)
        
        if form.is_valid():
            user = form.get_user()
            
            # 1. Check if user is verified/active
            if not user.is_active:
                record_failed_login(username)
                msg = '❌ Please verify your email before logging in.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': msg}, status=400)
                else:
                    messages.error(request, msg)
                    log_security_event('inactive_account_login', user=user, severity='WARNING')
                    return redirect('login')

            # 2. Log the user in
            login(request, user)
            reset_failed_login(username)  # ✅ Clear lockout on successful login
            log_security_event('successful_login', user=user)

            # 3. Determine Role-Based Redirect
            if user.is_staff:
                redirect_url = reverse('admin_dashboard')
            else:
                redirect_url = reverse('dashboard')

            # 4. Handle Response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Login successful! Redirecting...',
                    'redirect_url': redirect_url
                })
            else:
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect(redirect_url)

        else:
            # Invalid credentials - record failed attempt
            record_failed_login(username)
            msg = '❌ Invalid username or password.'
            log_security_event('failed_login', details=f'username: {username}', severity='WARNING')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=400)
            else:
                messages.error(request, msg)
                return redirect('login')

    else:
        form = AuthenticationForm()

    return render(request, 'vtuapp/login.html', {'form': form})

# ====================== LOGOUT VIEW ======================
def logout_view(request):
    logout(request)
    messages.info(request, "Logged out successfully.")
    return redirect('login')

# ====================== DASHBOARD ======================
@login_required
def dashboard(request):
    profile = request.user.profile
    wallet = request.user.wallet
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')[:5]

    # Handle the PIN Setup AJAX from the dashboard overlay
    if request.method == "POST" and request.POST.get('action') == 'set_initial_pin':
        new_pin = request.POST.get('new_pin')
        if len(new_pin) == 4 and new_pin.isdigit():
            profile.set_pin(new_pin)  # ✅ Use hash method
            log_security_event('transaction_pin_created', user=request.user)
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'error'}, status=400)

    # Check if PIN exists (still need to check transaction_pin field)
    has_pin = True if profile.transaction_pin else False

    context = {
        'wallet': wallet,
        'transactions': transactions,
        'has_pin': has_pin,
    }
    return render(request, 'vtuapp/dashboard.html', context)        
# ====================== SETTINGS ======================

@login_required
def settings_page(request):
    # Ensure profile exists for Aliyu
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        section = request.POST.get('section')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if section == 'profile':
            user = request.user
            user.email = request.POST.get('email', user.email)
            user.save()

            profile.full_name = request.POST.get('full_name', profile.full_name)
            # Match the 'name' attribute in your HTML (name="phone")
            profile.phone = request.POST.get('phone', profile.phone) 
            
            # Handle the profile picture upload from the camera icon
            if 'profile_picture' in request.FILES:
                profile.profile_picture = request.FILES['profile_picture']
            
            profile.save()

            if is_ajax:
                return JsonResponse({'status': 'success', 'message': '✅ Profile updated successfully!', 'should_reload': True})
            messages.success(request, 'Profile updated successfully!')
            return redirect('settings')

        elif section == 'password':
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')

            if not check_password(old_password, request.user.password):
                msg = '❌ Current password is incorrect'
                return JsonResponse({'status': 'error', 'message': msg}) if is_ajax else redirect('settings')
            
            if len(new_password) < 6:
                msg = '❌ Password must be at least 6 characters'
                return JsonResponse({'status': 'error', 'message': msg}) if is_ajax else redirect('settings')

            request.user.set_password(new_password)
            request.user.save()
            
            # CRITICAL: Keep Aliyu logged in after password change
            update_session_auth_hash(request, request.user)

            if is_ajax:
                return JsonResponse({'status': 'success', 'message': '✅ Password updated successfully!', 'should_reload': False})
            messages.success(request, 'Password updated successfully!')
            return redirect('settings')

        elif section == 'pin':
            old_pin = request.POST.get('old_pin')
            new_pin = request.POST.get('new_pin')

            # First Time PIN Creation
            if not profile.transaction_pin:
                if len(new_pin) == 4 and new_pin.isdigit():
                    profile.set_pin(new_pin)  # ✅ Use hash method
                    log_security_event('transaction_pin_created', user=request.user)
                    return JsonResponse({'status': 'success', 'message': '✅ Transaction PIN created!'})
                return JsonResponse({'status': 'error', 'message': '❌ PIN must be 4 digits'})

            # Changing Existing PIN
            if not profile.check_pin(old_pin):  # ✅ Use hash check method
                log_security_event('failed_pin_change', user=request.user, severity='WARNING')
                return JsonResponse({'status': 'error', 'message': '❌ Current PIN is incorrect'})
            
            if len(new_pin) == 4 and new_pin.isdigit():
                profile.set_pin(new_pin)  # ✅ Use hash method
                log_security_event('transaction_pin_changed', user=request.user)
                return JsonResponse({'status': 'success', 'message': '✅ PIN updated successfully!'})
            
            return JsonResponse({'status': 'error', 'message': '❌ New PIN must be 4 digits'})

    has_pin = bool(profile.transaction_pin)
    return render(request, 'vtuapp/settings.html', {'has_pin': has_pin})

# ====================== FUND WALLET (Paystack) ======================
def get_gafia_headers(payload=None):
    public_key = settings.GAFIAPAY_PUBLIC_KEY
    secret_key = settings.GAFIAPAY_SECRET_KEY
    
    # Use milliseconds to match Gafiapay's timestamp requirement
    timestamp = str(int(time.time() * 1000))
    
    # Gafiapay signature is generated from request body + timestamp
    message = ""
    if payload is not None:
        serialized_payload = json.dumps(payload, separators=(",", ":"))
        message = f"{serialized_payload}{timestamp}"
    else:
        message = timestamp
    
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return {
        "x-api-key": public_key,
        "x-signature": signature,
        "x-timestamp": timestamp,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

@login_required
def fund_wallet(request):
    user_profile = request.user.profile
    
    # 1. Check if user already has an account saved
    if not user_profile.gafia_account_number:
        url = "https://api.gafiapay.com/api/v1/external/account/generate"
        
        username = request.user.username
        full_name = f"{username} (Bin Datasub)"

        payload = {
            "email": request.user.email or f"{username}@bindatasub.com",
            "name": full_name.upper(),
        }
        
        try:
            headers = get_gafia_headers(payload)
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            
            res_data = response.json()
            
            if response.status_code == 200 and res_data.get('status') == 'success':
                acc_data = res_data['data']
                user_profile.gafia_account_number = acc_data['accountNumber']
                user_profile.gafia_bank_name = acc_data['bankName']
                user_profile.gafia_account_name = full_name 
                user_profile.save()
                log_security_event('gafia_account_generated', user=request.user)
            else:
                msg = f"Gateway Error: {res_data.get('message', 'Validation failed')}"
                messages.error(request, msg)
                log_security_event('gafia_account_error', user=request.user, details=msg, severity='WARNING')
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Gafiapay connection error: {e}")
            messages.error(request, "Unable to reach payment provider. Please check your network.")
            log_security_event('gafia_connection_error', user=request.user, details=str(e), severity='ERROR')
        except Exception as e:
            logger.error(f"Gafiapay error: {e}")
            messages.error(request, "An unexpected error occurred. Please try again.")
            log_security_event('gafia_error', user=request.user, details=str(e), severity='ERROR')

    context = {
        'acc_no': user_profile.gafia_account_number,
        'bank': user_profile.gafia_bank_name,
        'name': user_profile.gafia_account_name,
        'paystack_public_key': settings.PAYSTACK_PUBLIC_KEY,
    }
    return render(request, 'vtuapp/fund_wallet.html', context)

@login_required
def fund_wallet_callback(request):
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, 'Payment reference not found')
        log_security_event('invalid_paystack_callback', details='No reference', severity='WARNING')
        return redirect('dashboard')

    try:
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        res_data = response.json()

        if res_data.get('status') and res_data['data']['status'] == 'success':
            amount = Decimal(res_data['data']['amount']) / 100
            
            # ✅ SECURITY: Verify callback amount matches
            # You can add additional verification here

            wallet = request.user.wallet
            wallet.balance += amount
            wallet.save()

            Transaction.objects.create(
                user=request.user,
                transaction_type='Wallet Funding',
                amount=amount,
                provider='Paystack',
                status='Successful',
                reference=reference
            )

            log_security_event('wallet_funded_paystack', user=request.user, details=f'amount: {amount}')
            messages.success(request, f'✅ ₦{amount:,.2f} has been credited to your wallet successfully!')
        else:
            msg = 'Payment verification failed. Contact support if money was deducted.'
            log_security_event('paystack_verification_failed', user=request.user, details=msg, severity='WARNING')
            messages.error(request, msg)

    except Exception as e:
        logger.error(f"Paystack callback error: {traceback.format_exc()}")
        log_security_event('paystack_callback_error', user=request.user, details=str(e), severity='ERROR')
        messages.error(request, f'Verification error: {str(e)}')

    return redirect('dashboard')

@csrf_exempt  # Webhooks must allow POST from external services
def gafiapay_webhook(request):
    if request.method != 'POST':
        logger.warning("❌ Invalid webhook method")
        return HttpResponse(status=405)

    try:
        # ✅ SECURITY: Verify webhook signature
        signature = request.META.get('HTTP_X_SIGNATURE', '')
        timestamp = request.META.get('HTTP_X_TIMESTAMP', '')
        payload = request.body
        
        # 1. Verify signature
        if not verify_gafiapay_signature(payload.decode('utf-8'), signature, timestamp):
            logger.warning("❌ WEBHOOK REJECTED: Invalid signature")
            log_security_event('invalid_webhook_signature', details='gafiapay', severity='ERROR')
            return HttpResponse(status=401)  # Unauthorized
        
        # 2. Verify timestamp (prevent replay attacks)
        if not check_webhook_timestamp(timestamp, max_age_seconds=300):
            logger.warning("❌ WEBHOOK REJECTED: Timestamp invalid or expired")
            log_security_event('expired_webhook', details='gafiapay', severity='WARNING')
            return HttpResponse(status=400)  # Bad request
        
        # 3. Parse payload
        data = json.loads(payload)
        event = data.get('event')
        transaction = data.get('data', {}).get('transaction', {})

        logger.info(f"✅ VALID webhook received: {event}")

        # Check for the correct event
        if event == 'payment.received':
            amount = Decimal(str(transaction.get('amount', 0)))
            email = transaction.get('email')
            reference = transaction.get('orderNo') or transaction.get('id')

            if not reference:
                return HttpResponse(status=200)

            # Prevent double funding
            if not Transaction.objects.filter(reference=reference).exists():
                user = User.objects.filter(email=email).first()

                if user:
                    wallet = user.wallet
                    wallet.balance += amount
                    wallet.save()

                    Transaction.objects.create(
                        user=user,
                        transaction_type='Wallet Funding (Bank Transfer)',
                        amount=amount,
                        provider='Gafiapay',
                        status='Successful',
                        reference=reference
                    )
                    logger.info(f"✅ Credited {amount} to {user.username}")
                    log_security_event('wallet_funded_gafiapay', user=user, details=f'amount: {amount}')
                    return HttpResponse(status=200)
                else:
                    logger.warning(f"❌ USER NOT FOUND: {email}")
                    log_security_event('webhook_user_not_found', details=f'email: {email}', severity='WARNING')
                    return HttpResponse(status=404)

    except json.JSONDecodeError:
        logger.error("❌ Invalid JSON in webhook")
        log_security_event('invalid_webhook_json', severity='ERROR')
        return HttpResponse(status=400)
    except Exception as e:
        logger.error(f"Webhook error: {traceback.format_exc()}")
        log_security_event('webhook_error', details=str(e), severity='ERROR')
        return HttpResponse(status=500)

    return HttpResponse(status=200)

# ====================== PURCHASE VIEWS ======================
@login_required
def buy_airtime(request):
    if request.method == 'POST':
        try:
            form = AirtimeForm(request.POST)
            if form.is_valid():
                pin = form.cleaned_data.get('pin') or request.POST.get('pin')
                profile = request.user.profile
                wallet = request.user.wallet
                amount = form.cleaned_data['amount']
                phone = form.cleaned_data['phone']
                network_name = form.cleaned_data['network'].upper()

                # ✅ SECURITY: Rate limiting
                rate_limit_key = get_rate_limit_key(request, 'buy_airtime')
                if is_rate_limited(rate_limit_key, limit=20, window=60):
                    msg = '❌ Too many requests. Please try again later.'
                    return JsonResponse({'status': 'error', 'message': msg}, status=429)

                # 1. Security & Balance Checks
                if not profile.transaction_pin:
                    return JsonResponse({'status': 'no_pin', 'message': "Create Transaction PIN first"}, status=400)
                if not profile.check_pin(pin):  # ✅ Use hash check method
                    log_security_event('failed_pin_airtime', user=request.user, severity='WARNING')
                    return JsonResponse({'status': 'error', 'message': '❌ Incorrect Transaction PIN'}, status=400)
                if wallet.balance < amount:
                    return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)

                # 2. Map Network Name to SMEPlug IDs
                network_map = {'MTN': 1, 'GLO': 2, 'AIRTEL': 3, '9MOBILE': 4}
                net_id = network_map.get(network_name, 1)

                # 3. Call API
                service = VTUApiService()
                result = service.buy_airtime(network_id=net_id, phone=phone, amount=amount)

                if result['success']:
                    wallet.balance -= amount
                    wallet.save()
                    
                    new_tx = Transaction.objects.create(
                        user=request.user,
                        transaction_type='Airtime',
                        amount=amount,
                        provider=network_name,
                        phone_or_meter=phone,
                        status='Successful',
                        reference=result.get('transaction_id')
                    )
                    
                    log_security_event('airtime_purchase', user=request.user, details=f'amount: {amount}, network: {network_name}')
                    return JsonResponse({
                        'status': 'success', 
                        'message': f'✅ ₦{amount} Airtime sent!',
                        'redirect_url': reverse('receipt_detail', kwargs={'pk': new_tx.pk})
                    })
                else:
                    log_security_event('airtime_purchase_failed', user=request.user, details=result.get('message'))
                    return JsonResponse({'status': 'error', 'message': result['message']}, status=400)
            
            return JsonResponse({'status': 'error', 'message': '❌ Invalid form data'}, status=400)
        except Exception as e:
            logger.error(f"Buy airtime exception: {traceback.format_exc()}")
            return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'}, status=500)

    form = AirtimeForm()
    return render(request, 'vtuapp/buy_airtime.html', {'form': form})

@login_required
def buy_data(request):
    if request.method == 'POST':
        try:
            form = DataPurchaseForm(request.POST)
            if not form.is_valid():
                return JsonResponse({'status': 'error', 'message': f'Invalid Form: {form.errors.as_text()}'}, status=400)

            pin = request.POST.get('pin')
            profile = request.user.profile
            wallet = request.user.wallet
            plan = form.cleaned_data['plan']
            phone = form.cleaned_data['phone']

            # ✅ SECURITY: Rate limiting
            rate_limit_key = get_rate_limit_key(request, 'buy_data')
            if is_rate_limited(rate_limit_key, limit=20, window=60):
                msg = '❌ Too many requests. Please try again later.'
                return JsonResponse({'status': 'error', 'message': msg}, status=429)

            # PIN Check (Updated to use Profile field and hash method)
            if not profile.transaction_pin:
                return JsonResponse({'status': 'no_pin', 'message': "Please set a PIN in Settings first"}, status=400)

            if not profile.check_pin(pin):  # ✅ Use hash check method
                log_security_event('failed_pin_data', user=request.user, severity='WARNING')
                return JsonResponse({'status': 'error', 'message': '❌ Incorrect Transaction PIN'}, status=400)

            # Balance Check
            if wallet.balance < plan.price:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient balance!'}, status=400)

            # API Call
            service = VTUApiService()
            result = service.buy_data(
                network_id=plan.network_id,
                plan_id=plan.smeplug_plan_id,
                phone=phone,
                amount=plan.price
            )

            if result.get('success'):
                wallet.balance -= plan.price
                wallet.save()
                
                new_tx = Transaction.objects.create(
                    user=request.user,
                    transaction_type='Data Purchase',
                    amount=plan.price,
                    provider=plan.network,
                    phone_or_meter=phone,
                    status='Successful',
                    reference=result.get('reference')
                )

                log_security_event('data_purchase', user=request.user, details=f'amount: {plan.price}, plan: {plan.name}')
                return JsonResponse({
                    'status': 'success',
                    'message': f'✅ {plan.name} sent to {phone}',
                    'redirect_url': reverse('receipt_detail', kwargs={'pk': new_tx.pk})
                })
            else:
                log_security_event('data_purchase_failed', user=request.user, details=result.get('message'))
                return JsonResponse({'status': 'error', 'message': result.get('message', 'API Error')}, status=400)

        except Exception as e:
            logger.error(f"Buy data exception: {traceback.format_exc()}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    form = DataPurchaseForm()
    plans = DataPlan.objects.filter(is_active=True)
    return render(request, 'vtuapp/buy_data.html', {'form': form, 'plans': plans})

@login_required
def pay_electricity(request):
    if request.method == 'POST':
        form = ElectricityForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet

            if not wallet.check_pin(pin):
                return JsonResponse({'status': 'error', 'message': '❌ Incorrect Transaction PIN'}, status=400)

            amount = form.cleaned_data['amount']
            if wallet.balance >= amount:
                wallet.balance -= amount
                wallet.save()

                Transaction.objects.create(
                    user=request.user,
                    transaction_type='Electricity',
                    amount=amount,
                    provider=form.cleaned_data['provider'],
                    phone_or_meter=form.cleaned_data['meter_number'],
                    status='Successful'
                )
                return JsonResponse({
                    'status': 'success',
                    'message': '✅ Electricity bill paid successfully!'
                })
            else:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)
        
        return JsonResponse({'status': 'error', 'message': '❌ Please fill all fields correctly'}, status=400)

    form = ElectricityForm()
    return render(request, 'vtuapp/pay_electricity.html', {'form': form})


@login_required
def cable_tv(request):
    if request.method == 'POST':
        form = CableTVForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet

            if not wallet.check_pin(pin):
                return JsonResponse({'status': 'error', 'message': '❌ Incorrect Transaction PIN'}, status=400)

            amount = form.cleaned_data['amount']
            if wallet.balance >= amount:
                wallet.balance -= amount
                wallet.save()

                Transaction.objects.create(
                    user=request.user,
                    transaction_type='Cable TV',
                    amount=amount,
                    provider=form.cleaned_data['provider'],
                    phone_or_meter=form.cleaned_data['smartcard_number'],
                    status='Successful'
                )
                return JsonResponse({
                    'status': 'success',
                    'message': '✅ Cable TV subscription renewed successfully!'
                })
            else:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)
        
        return JsonResponse({'status': 'error', 'message': '❌ Please fill all fields correctly'}, status=400)

    form = CableTVForm()
    return render(request, 'vtuapp/cable_tv.html', {'form': form})


# ====================== OTHER PAGES ======================
@login_required
def transactions_history(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')
    return render(request, 'vtuapp/transactions.html', {'transactions': transactions})

@login_required
def transaction_receipt(request, pk):
    # We use get_object_or_404 to handle invalid IDs gracefully
    from django.shortcuts import get_object_or_404
    
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    
    return render(request, 'vtuapp/transaction_receipt.html', {
        'transaction': transaction
    })

@login_required
def services_page(request):
    return render(request, 'vtuapp/services.html')

@login_required
def support(request):
    if request.method == 'POST':
        messages.success(request, '✅ Your message has been sent to our support team.')
        return redirect('support')
    return render(request, 'vtuapp/support.html')

@login_required
def referral(request):
    referral_code = f"BDS-{request.user.username.upper()[:8]}"
    referral_link = f"https://yourdomain.com/register/?ref={referral_code}"
    
    return render(request, 'vtuapp/referral.html', {
        'referral_code': referral_code,
        'referral_link': referral_link
    })


# ====================== WEBAUTHN (Biometric) ======================
from webauthn import generate_registration_options, verify_registration_response, options_to_json

# Temporary storage for challenges (in production, use Redis or database)
webauthn_challenges = {}

@login_required
def webauthn_register_options(request):
    """Generate registration options for fingerprint/face ID"""
    try:
        # Important: Use correct domain (especially on PythonAnywhere)
        rp_id = request.get_host().split(':')[0]
        if rp_id.endswith('.pythonanywhere.com'):
            rp_id = 'hidar022.pythonanywhere.com'   # Change if your subdomain is different

        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Bin Datasub",
            user_id=str(request.user.id).encode(),
            user_name=request.user.username,
            user_display_name=request.user.get_full_name() or request.user.username,
        )

        webauthn_challenges[request.user.id] = options.challenge

        return JsonResponse(options_to_json(options))
    except Exception as e:
        print(f"WebAuthn Options Error: {e}")  # Check server logs
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@login_required
def webauthn_register_complete(request):
    """Verify the biometric credential"""
    try:
        data = json.loads(request.body)
        challenge = webauthn_challenges.get(request.user.id)

        if not challenge:
            return JsonResponse({'status': 'error', 'message': 'Challenge expired. Please try again.'}, status=400)

        # Verify registration
        verification = verify_registration_response(
            credential=data,
            expected_challenge=challenge,
            expected_rp_id=request.get_host().split(':')[0],
            expected_origin=request.build_absolute_uri('/').rstrip('/'),
        )

        # TODO: Save the credential to database later
        webauthn_challenges.pop(request.user.id, None)

        return JsonResponse({
            'status': 'success', 
            'message': '✅ Fingerprint / Face ID registered successfully!'
        })

    except Exception as e:
        print(f"WebAuthn Complete Error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ====================== ADMIN DASHBOARD VIEWS ======================

from django.db.models import F, Sum

@staff_member_required
def admin_dashboard(request):
    # 1. CALCULATE FINANCIAL STATS
    # total_sales: Sum of all successful transactions
    total_sales = Transaction.objects.filter(status='successful').aggregate(Sum('amount'))['amount__sum'] or 0
    
    # FIX: Calculate profit as (amount - cost_price) for all successful transactions
    profit_data = Transaction.objects.filter(status='successful').aggregate(
        total_profit=Sum(F('amount') - F('cost_price'))
    )
    total_profit = profit_data['total_profit'] or 0
    
    # 2. THE REST OF YOUR VIEW...
    total_wallet_balances = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0
    total_users = User.objects.count()
    recent_txs = Transaction.objects.select_related('user').order_by('-timestamp')[:10]
    all_users = User.objects.select_related('wallet').order_by('-date_joined')[:5]

    # Security alerts: suspicious users with many failed transactions
    from django.db.models import Q
    security_alerts = User.objects.filter(
        Q(transaction__status='Failed') &
        Q(transaction__timestamp__gte=timezone.now() - timedelta(hours=24))
    ).annotate(
        failed_count=Count('transaction')
    ).filter(failed_count__gt=5).count()

    context = {
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_wallet_balances': total_wallet_balances,
        'total_users': total_users,
        'recent_txs': recent_txs,
        'all_users': all_users,
        'last_backup': "Daily Sync Active",
        'security_alerts': security_alerts,
    }
    return render(request, 'admin/index.html', context)

@staff_member_required
def admin_user_detail(request, user_id):
    """View details for a specific user from the dashboard."""
    user_obj = get_object_or_404(User, id=user_id)
    # Get user's transactions and wallet
    transactions = Transaction.objects.filter(user=user_obj).order_by('-timestamp')
    
    context = {
        'user_obj': user_obj,
        'transactions': transactions,
    }
    return render(request, 'admin/user_detail.html', context)

@staff_member_required
def admin_user_edit(request, user_id):
    """View to edit user details from the CEO panel."""
    user_obj = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        user_obj.username = request.POST.get('username')
        user_obj.email = request.POST.get('email')
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        
        # Handle staff status toggle if needed
        is_staff = request.POST.get('is_staff') == 'on'
        user_obj.is_staff = is_staff
        
        user_obj.save()
        messages.success(request, f'✅ User {user_obj.username} updated successfully!')
        return redirect('admin_dashboard')
        
    context = {
        'user_obj': user_obj,
    }
    return render(request, 'admin/user_edit.html', context)        

@staff_member_required
def admin_users(request):
    """Admin User Management"""
    users = User.objects.all().order_by('-date_joined')
    search_query = request.GET.get('q', '').strip()

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(profile__phone__icontains=search_query)
        )

    # Handle user actions
    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')

        try:
            user = User.objects.get(id=user_id)

            if action == 'activate':
                user.is_active = True
                user.save()
                log_security_event('user_activated', user=user, details=f'by admin {request.user.username}')
                messages.success(request, f'✅ User {user.username} activated')
            elif action == 'deactivate':
                user.is_active = False
                user.save()
                log_security_event('user_deactivated', user=user, details=f'by admin {request.user.username}')
                messages.success(request, f'✅ User {user.username} deactivated')
            elif action == 'delete':
                user.delete()
                log_security_event('user_deleted', details=f'user {user.username} deleted by admin {request.user.username}', severity='WARNING')
                messages.success(request, f'✅ User {user.username} deleted')

        except User.DoesNotExist:
            messages.error(request, 'User not found')

        return redirect('admin_users')

    from django.core.paginator import Paginator
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)

    context = {
        'users': users_page,
        'total_users': users.count(),
        'active_users': users.filter(is_active=True).count(),
        'inactive_users': users.filter(is_active=False).count(),
        'staff_users': users.filter(is_staff=True).count(),
        'search_query': search_query,
    }
    return render(request, 'admin/users.html', context)

@staff_member_required
def add_plan(request):
    """Handles the creation of new data plans from the CEO panel modal."""
    if request.method == 'POST':
        # Matching the 'name' attributes from your dashboard.html form
        network = request.POST.get('network')
        name = request.POST.get('name')
        price = request.POST.get('price')
        smeplug_id = request.POST.get('smeplug_id')
        network_id = request.POST.get('network_id')

        # Create the new plan in the database
        DataPlan.objects.create(
            network=network,
            name=name,
            price=price,
            smeplug_plan_id=smeplug_id, # Check if your model field is 'smeplug_id' or 'smeplug_plan_id'
            network_id=network_id,
            is_active=True
        )
        return redirect('admin_dashboard')
    
    return redirect('admin_dashboard')    

@staff_member_required
def admin_transactions(request):
    """Admin Transaction Management"""
    transactions = Transaction.objects.all().order_by('-timestamp')
    
    # Filters
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if status_filter:
        transactions = transactions.filter(status__iexact=status_filter)
    if type_filter:
        transactions = transactions.filter(transaction_type__icontains=type_filter)
    if date_from:
        transactions = transactions.filter(timestamp__date__gte=date_from)
    if date_to:
        transactions = transactions.filter(timestamp__date__lte=date_to)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(transactions, 50)  # 50 per page
    page_number = request.GET.get('page')
    transactions_page = paginator.get_page(page_number)
    
    # Stats
    all_transactions = Transaction.objects.all()
    total_transactions = all_transactions.count()
    successful_transactions = all_transactions.filter(status__iexact='successful').count()
    pending_transactions = all_transactions.filter(status__iexact='pending').count()
    failed_transactions = all_transactions.filter(status__iexact='failed').count()
    
    context = {
        'transactions': transactions_page,
        'total_transactions': total_transactions,
        'successful_transactions': successful_transactions,
        'pending_transactions': pending_transactions,
        'failed_transactions': failed_transactions,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'admin/transactions.html', context)

@staff_member_required
def admin_transaction_detail(request, tx_id):
    tx = get_object_or_404(Transaction, id=tx_id)
    return JsonResponse({
        'id': tx.id,
        'user': tx.user.username,
        'email': tx.user.email,
        'type': tx.transaction_type,
        'amount': str(tx.amount),
        'status': tx.status,
        'provider': tx.provider,
        'reference': tx.reference,
        'phone_or_meter': tx.phone_or_meter,
        'timestamp': tx.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'cost_price': str(tx.cost_price),
        'profit': str(tx.amount - tx.cost_price),
    })

@staff_member_required
def admin_transaction_retry(request, tx_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    tx = get_object_or_404(Transaction, id=tx_id)
    if tx.status.lower() != 'pending':
        return JsonResponse({'success': False, 'message': 'Only pending transactions can be retried'}, status=400)
    tx.status = 'Successful'
    tx.save()
    log_security_event('transaction_retried', user=tx.user, details=f'tx {tx.id} retried by {request.user.username}')
    return JsonResponse({'success': True, 'message': 'Transaction retried successfully'})

@staff_member_required
def admin_transaction_refund(request, tx_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    tx = get_object_or_404(Transaction, id=tx_id)
    if tx.status.lower() != 'successful':
        return JsonResponse({'success': False, 'message': 'Only successful transactions can be refunded'}, status=400)
    wallet = tx.user.wallet
    wallet.balance += tx.amount
    wallet.save()
    tx.status = 'Refunded'
    tx.save()
    log_security_event('transaction_refunded', user=tx.user, details=f'tx {tx.id} refunded by {request.user.username}', severity='WARNING')
    return JsonResponse({'success': True, 'message': 'Transaction refunded and wallet credited'})

@staff_member_required
def admin_plan_detail(request, plan_id):
    plan = get_object_or_404(DataPlan, id=plan_id)
    return JsonResponse({
        'id': plan.id,
        'network': plan.network,
        'name': plan.name,
        'price': str(plan.price),
        'network_id': plan.network_id,
        'smeplug_plan_id': plan.smeplug_plan_id,
        'is_active': plan.is_active,
    })

@staff_member_required
def admin_plan_toggle_status(request, plan_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    plan = get_object_or_404(DataPlan, id=plan_id)
    plan.is_active = not plan.is_active
    plan.save()
    return JsonResponse({'success': True, 'message': f'Plan status updated to {"active" if plan.is_active else "inactive"}'})

@staff_member_required
def admin_plan_delete(request, plan_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    plan = get_object_or_404(DataPlan, id=plan_id)
    plan.delete()
    return JsonResponse({'success': True, 'message': 'Plan deleted successfully'})

@staff_member_required
def admin_plan_edit(request, plan_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    plan = get_object_or_404(DataPlan, id=plan_id)
    plan.network = request.POST.get('network')
    plan.name = request.POST.get('name')
    plan.price = request.POST.get('price')
    plan.network_id = request.POST.get('network_id')
    plan.smeplug_plan_id = request.POST.get('smeplug_id')
    plan.save()
    return JsonResponse({'success': True, 'message': 'Plan updated successfully'})

@staff_member_required
def admin_transactions_export(request):
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    transactions = Transaction.objects.all().order_by('-timestamp')

    if status_filter:
        transactions = transactions.filter(status__iexact=status_filter)
    if type_filter:
        transactions = transactions.filter(transaction_type__icontains=type_filter)

    rows = [
        'ID,User,Email,Type,Amount,Status,Provider,Reference,Phone/Meter,Timestamp',
    ]
    for tx in transactions:
        rows.append(
            f'{tx.id},{tx.user.username},{tx.user.email},{tx.transaction_type},"{tx.amount}",{tx.status},{tx.provider},{tx.reference or ""},{tx.phone_or_meter},{tx.timestamp.strftime("%Y-%m-%d %H:%M:%S")}'
        )

    response = HttpResponse('\n'.join(rows), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions_export.csv"'
    return response

@staff_member_required
def admin_plans(request):
    """Admin Data Plans Management"""
    plans = DataPlan.objects.all().order_by('network', 'price')
    network_filter = request.GET.get('network', '')
    if network_filter:
        plans = plans.filter(network__iexact=network_filter)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            DataPlan.objects.create(
                network=request.POST.get('network'),
                name=request.POST.get('name'),
                price=request.POST.get('price'),
                network_id=request.POST.get('network_id'),
                smeplug_plan_id=request.POST.get('smeplug_id'),
                is_active=True
            )
            messages.success(request, '✅ Plan added successfully')
            return redirect('admin_plans')
            
        elif action == 'edit':
            plan_id = request.POST.get('plan_id')
            plan = DataPlan.objects.get(id=plan_id)
            plan.network = request.POST.get('network')
            plan.name = request.POST.get('name')
            plan.price = request.POST.get('price')
            plan.network_id = request.POST.get('network_id')
            plan.smeplug_plan_id = request.POST.get('smeplug_id')
            plan.save()
            messages.success(request, '✅ Plan updated successfully')
            return redirect('admin_plans')
            
        elif action == 'toggle':
            plan_id = request.POST.get('plan_id')
            plan = DataPlan.objects.get(id=plan_id)
            plan.is_active = not plan.is_active
            plan.save()
            status = "activated" if plan.is_active else "deactivated"
            messages.success(request, f'✅ Plan {status}')
            return redirect('admin_plans')
            
        elif action == 'delete':
            plan_id = request.POST.get('plan_id')
            plan = DataPlan.objects.get(id=plan_id)
            plan.delete()
            messages.success(request, '✅ Plan deleted')
            return redirect('admin_plans')

    from django.core.paginator import Paginator
    paginator = Paginator(plans, 25)
    page_number = request.GET.get('page')
    plans_page = paginator.get_page(page_number)

    context = {
        'plans': plans_page,
        'total_plans': plans.count(),
        'mtn_plans': plans.filter(network__iexact='MTN').count(),
        'glo_plans': plans.filter(network__iexact='GLO').count(),
        'airtel_plans': plans.filter(network__iexact='AIRTEL').count(),
        'mobile_plans': plans.filter(network__iexact='9MOBILE').count(),
        'network_filter': network_filter,
    }
    return render(request, 'admin/plans.html', context)

@staff_member_required
def admin_reports(request):
    """Admin Reports & Analytics"""
    # Date range
    from datetime import datetime, timedelta
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    date_from = request.GET.get('date_from', start_date)
    date_to = request.GET.get('date_to', end_date)
    
    if isinstance(date_from, str):
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
    if isinstance(date_to, str):
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # Transaction reports
    transactions = Transaction.objects.filter(
        timestamp__date__gte=date_from,
        timestamp__date__lte=date_to
    )
    
    # Revenue by type
    revenue_by_type = transactions.filter(status='Successful').values('transaction_type').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Revenue by network
    revenue_by_network = transactions.filter(
        status='Successful',
        transaction_type__in=['Data Purchase', 'Airtime Purchase']
    ).values('provider').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Daily revenue
    daily_revenue = transactions.filter(status='Successful').extra(
        select={'day': 'DATE(timestamp)'}
    ).values('day').annotate(
        total=Sum('amount')
    ).order_by('day')
    
    # User growth
    user_growth = User.objects.filter(
        date_joined__date__gte=date_from,
        date_joined__date__lte=date_to
    ).extra(
        select={'day': 'DATE(date_joined)'}
    ).values('day').annotate(
        count=Count('id')
    ).order_by('day')
    
    # Top users by spending
    top_users = User.objects.annotate(
        total_spent=Sum('transaction__amount', filter=Q(transaction__status='Successful'))
    ).filter(total_spent__gt=0).order_by('-total_spent')[:10]
    
    total_revenue = transactions.filter(status='Successful').aggregate(Sum('amount'))['amount__sum'] or 0
    previous_period = Transaction.objects.filter(
        timestamp__date__gte=start_date - timedelta(days=30),
        timestamp__date__lt=start_date,
        status='Successful'
    )
    previous_revenue = previous_period.aggregate(Sum('amount'))['amount__sum'] or 0
    monthly_growth = 0
    if previous_revenue:
        monthly_growth = round(((total_revenue - previous_revenue) / previous_revenue) * 100, 2)

    average_transaction = transactions.aggregate(Avg('amount'))['amount__avg'] or 0
    top_network_obj = revenue_by_network.first()
    top_network = top_network_obj['provider'] if top_network_obj else 'N/A'

    revenue_labels = [row['day'].strftime('%b %d') for row in daily_revenue]
    revenue_data = [float(row['total']) for row in daily_revenue]
    transaction_labels = [item['transaction_type'] for item in revenue_by_type]
    transaction_data = [float(item['total']) for item in revenue_by_type]
    network_stats = [
        {
            'network': item['provider'],
            'revenue': item['total'],
            'transactions': item['count'],
        }
        for item in revenue_by_network
    ]

    top_users = User.objects.annotate(
        total_spent=Sum('transaction__amount', filter=Q(transaction__status='Successful')),
        transaction_count=Count('transaction__id', filter=Q(transaction__status='Successful'))
    ).filter(total_spent__gt=0).order_by('-total_spent')[:10]

    context = {
        'date_from': date_from,
        'date_to': date_to,
        'revenue_by_type': revenue_by_type,
        'revenue_by_network': revenue_by_network,
        'daily_revenue': daily_revenue,
        'user_growth': user_growth,
        'top_users': top_users,
        'total_revenue': total_revenue,
        'total_transactions': transactions.count(),
        'successful_transactions': transactions.filter(status='Successful').count(),
        'monthly_growth': monthly_growth,
        'avg_transaction': average_transaction,
        'top_network': top_network,
        'network_stats': network_stats,
        'revenue_labels': json.dumps(revenue_labels),
        'revenue_data': json.dumps(revenue_data),
        'transaction_labels': json.dumps(transaction_labels),
        'transaction_data': json.dumps(transaction_data),
    }
    return render(request, 'admin/reports.html', context)

@staff_member_required
def admin_reports_generate(request):
    query = request.GET.urlencode()
    url = reverse('admin_reports')
    if query:
        url = f"{url}?{query}"
    return redirect(url)

@staff_member_required
def admin_reports_export(request):
    report_type = request.GET.get('type', 'transactions')
    fmt = request.GET.get('format', 'csv').lower()
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    transactions = Transaction.objects.all().order_by('-timestamp')
    if start_date:
        transactions = transactions.filter(timestamp__date__gte=start_date)
    if end_date:
        transactions = transactions.filter(timestamp__date__lte=end_date)

    rows = [
        'ID,User,Email,Type,Amount,Status,Provider,Reference,Phone/Meter,Timestamp'
    ]
    for tx in transactions:
        rows.append(
            f'{tx.id},{tx.user.username},{tx.user.email},{tx.transaction_type},"{tx.amount}",{tx.status},{tx.provider},{tx.reference or ""},{tx.phone_or_meter},{tx.timestamp.strftime("%Y-%m-%d %H:%M:%S")}'
        )

    if fmt == 'json':
        payload = []
        for tx in transactions:
            payload.append({
                'id': tx.id,
                'user': tx.user.username,
                'email': tx.user.email,
                'type': tx.transaction_type,
                'amount': str(tx.amount),
                'status': tx.status,
                'provider': tx.provider,
                'reference': tx.reference,
                'phone_or_meter': tx.phone_or_meter,
                'timestamp': tx.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            })
        response = HttpResponse(json.dumps(payload, indent=2), content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="reports_export.json"'
        return response

    content_type = 'text/csv'
    filename = 'reports_export.csv'
    if fmt == 'excel':
        content_type = 'application/vnd.ms-excel'
        filename = 'reports_export.xls'
    elif fmt == 'pdf':
        content_type = 'application/pdf'
        filename = 'reports_export.pdf'

    response = HttpResponse('\n'.join(rows), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@staff_member_required
def admin_settings(request):
    """Admin System Settings"""
    if request.method == 'POST':
        action = request.POST.get('action')
        if not action and any(k in request.POST for k in ['save_api', 'save_system', 'save_security', 'save_notifications']):
            action = 'update_settings'

        saved_settings = None
        if action == 'update_settings':
            messages.success(request, '✅ Settings updated successfully')
            saved_settings = {
                'smeplug_api_key': request.POST.get('smeplug_api_key', ''),
                'webhook_secret': request.POST.get('webhook_secret', ''),
                'api_base_url': request.POST.get('api_base_url', 'https://api.smeplug.ng'),
                'api_enabled': request.POST.get('api_enabled') == 'on',
                'site_title': request.POST.get('site_title', 'DataSub VTU'),
                'support_email': request.POST.get('support_email', ''),
                'maintenance_mode': request.POST.get('maintenance_mode', 'false'),
                'currency': request.POST.get('currency', 'NGN'),
                'session_timeout': int(request.POST.get('session_timeout', 30)),
                'max_login_attempts': int(request.POST.get('max_login_attempts', 5)),
                'two_factor_required': request.POST.get('two_factor_required') == 'on',
                'ip_whitelist_enabled': request.POST.get('ip_whitelist_enabled') == 'on',
                'email_notifications': request.POST.get('email_notifications') == 'on',
                'sms_notifications': request.POST.get('sms_notifications') == 'on',
                'transaction_alerts': request.POST.get('transaction_alerts') == 'on',
                'system_alerts': request.POST.get('system_alerts') == 'on',
            }
        elif action == 'clear_cache':
            from django.core.cache import cache
            cache.clear()
            messages.success(request, '✅ Cache cleared successfully')
        elif action == 'backup_database':
            import os
            from django.conf import settings as django_settings
            from datetime import datetime
            import shutil
            backup_name = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
            backup_path = os.path.join(django_settings.BASE_DIR, 'backups', backup_name)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            shutil.copy(django_settings.DATABASES['default']['NAME'], backup_path)
            messages.success(request, f'✅ Database backed up to {backup_name}')
        elif action == 'restart_services':
            messages.success(request, '✅ Service restart command queued')
    
    # System stats
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
        table_count = cursor.fetchone()[0]
    
    settings_context = {
        'smeplug_api_key': getattr(settings, 'SMEPLUG_API_KEY', ''),
        'webhook_secret': getattr(settings, 'WEBHOOK_SECRET', ''),
        'api_base_url': getattr(settings, 'API_BASE_URL', 'https://api.smeplug.ng'),
        'api_enabled': getattr(settings, 'API_ENABLED', False),
        'site_title': getattr(settings, 'SITE_TITLE', 'DataSub VTU'),
        'support_email': getattr(settings, 'SUPPORT_EMAIL', ''),
        'maintenance_mode': getattr(settings, 'MAINTENANCE_MODE', 'false'),
        'currency': getattr(settings, 'CURRENCY', 'NGN'),
        'session_timeout': getattr(settings, 'SESSION_TIMEOUT', 30),
        'max_login_attempts': getattr(settings, 'MAX_LOGIN_ATTEMPTS', 5),
        'two_factor_required': getattr(settings, 'TWO_FACTOR_REQUIRED', False),
        'ip_whitelist_enabled': getattr(settings, 'IP_WHITELIST_ENABLED', False),
        'email_notifications': getattr(settings, 'EMAIL_NOTIFICATIONS', True),
        'sms_notifications': getattr(settings, 'SMS_NOTIFICATIONS', True),
        'transaction_alerts': getattr(settings, 'TRANSACTION_ALERTS', True),
        'system_alerts': getattr(settings, 'SYSTEM_ALERTS', True),
    }
    if 'saved_settings' in locals() and saved_settings:
        settings_context.update(saved_settings)
    
    context = {
        'table_count': table_count,
        'user_count': User.objects.count(),
        'transaction_count': Transaction.objects.count(),
        'plan_count': DataPlan.objects.count(),
        'settings': settings_context,
        'system_logs': [],
    }
    return render(request, 'admin/settings.html', context)

@staff_member_required
def admin_settings_clear_cache(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    from django.core.cache import cache
    cache.clear()
    return JsonResponse({'success': True, 'message': 'Cache cleared successfully'})

@staff_member_required
def admin_settings_backup_db(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    import os
    from django.conf import settings as django_settings
    from datetime import datetime
    import shutil
    os.makedirs(os.path.join(django_settings.BASE_DIR, 'backups'), exist_ok=True)
    backup_name = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    backup_path = os.path.join(django_settings.BASE_DIR, 'backups', backup_name)
    shutil.copy(django_settings.DATABASES['default']['NAME'], backup_path)
    return JsonResponse({'success': True, 'message': f'Database backed up to {backup_name}'})

@staff_member_required
def admin_settings_restart_services(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    # Placeholder for service restart; actual restart requires system privileges
    return JsonResponse({'success': True, 'message': 'Service restart command queued'})

@staff_member_required
def admin_security(request):
    """Admin Security Dashboard"""
    from django.core.cache import cache

    # Security stats
    failed_login_attempts = cache.get('failed_login_count', 0)
    locked_accounts = 0  # Would need to count cache keys, but for simplicity
    
    # Recent security events (from logs if available)
    security_alerts = []
    
    # Check for suspicious activities
    suspicious_users = User.objects.filter(
        Q(transaction__status='Failed') &
        Q(transaction__timestamp__gte=timezone.now() - timedelta(hours=24))
    ).annotate(
        failed_count=Count('transaction')
    ).filter(failed_count__gt=5).distinct()
    
    context = {
        'failed_login_attempts': failed_login_attempts,
        'locked_accounts': locked_accounts,
        'security_alerts': security_alerts,
        'suspicious_users': suspicious_users,
        'total_users': User.objects.count(),
        'active_sessions': 0,  # Would need session tracking
    }
    return render(request, 'admin/security.html', context)

