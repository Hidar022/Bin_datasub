# 1. Standard Library Imports
import json
import hmac
import hashlib
import logging
import random
import traceback
import requests
from decimal import Decimal
from datetime import timedelta
from django.http import HttpResponse
from django.db.models import Sum
from django.contrib.admin.views.decorators import staff_member_required
import time

from .models import DataPlan

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

# 3. Local Project Imports (Services, Models, and Forms)
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

def home_redirect(request):
    return redirect('login') if not request.user.is_authenticated else redirect('dashboard')


# ====================== AUTH ======================

@staff_member_required
def add_plan(request):
    if request.method == 'POST':
        # Get data from the Terminal Modal
        network = request.POST.get('network')
        name = request.POST.get('name')
        price = request.POST.get('price')
        sme_id = request.POST.get('smeplug_id')
        net_id = request.POST.get('network_id')

        # Save to Database
        DataPlan.objects.create(
            network=network,
            name=name,
            price=price,
            smeplug_plan_id=sme_id,
            network_id=net_id,
            is_active=True
        )
        return redirect('admin_dashboard')

@staff_member_required
def admin_dashboard(request):
    # Stats
    sales_data = Transaction.objects.filter(status='Successful').exclude(transaction_type='Wallet Funding')
    total_sales = sales_data.aggregate(Sum('amount'))['amount__sum'] or 0
    total_cost = sales_data.aggregate(Sum('cost_price'))['cost_price__sum'] or 0
    total_profit = total_sales - total_cost
    
    # User Stats
    total_users = User.objects.count()
    total_wallet_balances = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0
    
    # Data Lists
    recent_txs = Transaction.objects.all().order_by('-timestamp')[:15]
    all_users = User.objects.all().order_by('-date_joined')[:10] # Latest 10 users

    context = {
        'total_sales': total_sales,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'total_users': total_users,
        'total_wallet_balances': total_wallet_balances,
        'recent_txs': recent_txs,
        'all_users': all_users,
    }
    return render(request, 'vtuapp/admin_dashboard.html', context)

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

            # === Normal Registration (email doesn't exist) ===
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            otp = str(random.randint(100000, 999999))
            profile, _ = Profile.objects.get_or_create(user=user)
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

                return JsonResponse({
                    'success': True,
                    'message': '✅ Email verified successfully! Redirecting to dashboard...'
                })
            else:
                return JsonResponse({'success': False, 'message': '❌ Incorrect OTP. Please try again.'}, status=400)

        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'User not found. Please register again.'}, status=400)
        except Profile.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Profile not found. Please register again.'}, status=400)
        except Exception as e:
            print(f"OTP Verification Error: {e}")   # ← This will show in your terminal
            return JsonResponse({'success': False, 'message': f'Something went wrong: {str(e)}'}, status=400)

    return render(request, 'vtuapp/verify_otp.html', {})

# ====================== LOGIN VIEW ======================
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        
        if form.is_valid():
            user = form.get_user()
            
            # 1. Check if user is verified/active
            if not user.is_active:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': '❌ Please verify your email before logging in.'
                    }, status=400)
                else:
                    messages.error(request, 'Please verify your email before logging in.')
                    return redirect('login')

            # 2. Log the user in
            login(request, user)

            # 3. Determine Role-Based Redirect
            # If you (aliyu) login, you go to CEO panel. Others go to dashboard.
            if user.is_staff:
                redirect_url = reverse('admin_dashboard')
            else:
                redirect_url = reverse('dashboard')

            # 4. Handle Response based on request type
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Login successful! Redirecting...',
                    'redirect_url': redirect_url  # Passing the role-based URL here
                })
            else:
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect(redirect_url)

        else:
            # Invalid credentials
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': '❌ Invalid username or password.'
                }, status=400)
            else:
                messages.error(request, 'Invalid username or password.')
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
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')[:4]
    return render(request, 'vtuapp/dashboard.html', {
        'wallet': wallet,
        'transactions': transactions
    })


# ====================== SETTINGS ======================
@login_required
def settings_page(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        section = request.POST.get('section')

        if section == 'profile':
            user = request.user
            user.email = request.POST.get('email', user.email)
            user.save()

            profile.full_name = request.POST.get('full_name', profile.full_name)
            profile.phone = request.POST.get('phone', profile.phone)
            if request.POST.get('dob'):
                profile.dob = request.POST.get('dob')
            profile.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'message': '✅ Profile updated successfully!'})
            else:
                messages.success(request, 'Profile updated successfully!')
                return redirect('settings')

        elif section == 'password':
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if not check_password(old_password, request.user.password):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': '❌ Current password is incorrect'})
                else:
                    messages.error(request, 'Current password is incorrect')
                    return redirect('settings')
            elif new_password != confirm_password:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': '❌ New passwords do not match'})
                else:
                    messages.error(request, 'New passwords do not match')
                    return redirect('settings')
            elif len(new_password) < 6:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': '❌ Password must be at least 6 characters'})
                else:
                    messages.error(request, 'Password must be at least 6 characters')
                    return redirect('settings')
            else:
                request.user.set_password(new_password)
                request.user.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'message': '✅ Account password updated successfully!'})
                else:
                    messages.success(request, 'Account password updated successfully!')
                    return redirect('settings')

        elif section == 'pin':
            old_pin = request.POST.get('old_pin')
            new_pin = request.POST.get('new_pin')
            wallet = request.user.wallet

            # --- Logic for First Time PIN Creation ---
            if not wallet.pin:
                if len(new_pin) == 4 and new_pin.isdigit():
                    wallet.set_pin(new_pin)
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'success', 
                            'message': '✅ Transaction PIN created successfully!'
                        })
                    else:
                        messages.success(request, 'Transaction PIN created successfully!')
                        return redirect('settings')
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'error', 
                            'message': '❌ PIN must be exactly 4 digits'
                        }, status=400)
                    else:
                        messages.error(request, 'PIN must be exactly 4 digits')
                        return redirect('settings')

            # --- Logic for Normal PIN Change ---
            if not wallet.check_pin(old_pin): 
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': '❌ Current PIN is incorrect'}, status=400)
                else:
                    messages.error(request, 'Current PIN is incorrect')
                    return redirect('settings')
            elif len(new_pin) != 4 or not new_pin.isdigit():
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': '❌ New PIN must be exactly 4 digits'}, status=400)
                else:
                    messages.error(request, 'New PIN must be exactly 4 digits')
                    return redirect('settings')
            else:
                wallet.set_pin(new_pin)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success', 
                        'message': '✅ Transaction PIN updated successfully!'
                    })
                else:
                    messages.success(request, 'Transaction PIN updated successfully!')
                    return redirect('settings')

    has_pin = bool(request.user.wallet.pin)
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
    
    print("GAFIA SIGNATURE MESSAGE:", message)
    print("GAFIA SIGNATURE:", signature)
    
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
        
        # Ensure name has at least two parts (First Last)
        full_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not full_name or len(full_name.split()) < 2:
            full_name = f"{request.user.username} CUSTOMER"

        # Add website name for bank statement clarity
        full_name = f"{full_name}(bindatasub)"

        payload = {
            "email": request.user.email or f"{request.user.username}@bindatasub.com",
            "name": full_name.upper(),
        }
        
        try:
            # Generate headers right before the request to minimize timestamp issues
            headers = get_gafia_headers(payload)
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            
            # Debugging: Print this to your console/terminal
            print(f"GAFIA REQUEST PAYLOAD: {json.dumps(payload, separators=(',', ':'), sort_keys=True)}")
            print(f"GAFIA RESPONSE STATUS: {response.status_code}")
            print(f"GAFIA RESPONSE BODY: {response.text}")
            
            res_data = response.json()
            
            if response.status_code == 200 and res_data.get('status') == 'success':
                acc_data = res_data['data']
                user_profile.gafia_account_number = acc_data['accountNumber']
                user_profile.gafia_bank_name = acc_data['bankName']
                user_profile.gafia_account_name = acc_data['accountName']
                user_profile.save()
            else:
                messages.error(request, f"Gateway Error: {res_data.get('message', 'Validation failed')}")
        
        except requests.exceptions.RequestException as e:
            # This catches DNS, Connection, and Timeout errors
            print(f"CONNECTION ERROR: {e}")
            messages.error(request, "Unable to reach payment provider. Please check your network.")
        except Exception as e:
            print(f"GENERAL ERROR: {e}")
            messages.error(request, "An unexpected error occurred. Please try again.")

    context = {
        'acc_no': user_profile.gafia_account_number,
        'bank': user_profile.gafia_bank_name,
        'name': user_profile.gafia_account_name,
    }
    return render(request, 'vtuapp/fund_wallet.html', context)

@login_required
def fund_wallet_callback(request):
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, 'Payment reference not found')
        return redirect('dashboard')

    try:
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        }
        
        response = requests.get(url, headers=headers)
        res_data = response.json()

        if res_data.get('status') and res_data['data']['status'] == 'success':
            amount = Decimal(res_data['data']['amount']) / 100

            wallet = request.user.wallet
            wallet.balance += amount
            wallet.save()

            Transaction.objects.create(
                user=request.user,
                transaction_type='Wallet Funding',
                amount=amount,
                provider='Paystack',
                status='Successful'
            )

            messages.success(request, f'✅ ₦{amount:,.2f} has been credited to your wallet successfully!')
        else:
            messages.error(request, 'Payment verification failed. Contact support if money was deducted.')

    except Exception as e:
        messages.error(request, f'Verification error: {str(e)}')

    return redirect('dashboard')

@csrf_exempt
def gafiapay_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    payload = request.body
    signature = request.headers.get('X-Gafiapay-Signature')
    
    # Log webhook receipt for debugging
    with open('/tmp/gafia_webhook.log', 'a') as f:
        f.write(f"[{timezone.now()}] Webhook received\n")
        f.write(f"Signature: {signature}\n")
        f.write(f"Payload: {payload.decode('utf-8', errors='replace')}\n")
        f.write("="*80 + "\n")
    
    print("GAFIA WEBHOOK SIGNATURE:", signature)
    print("GAFIA WEBHOOK PAYLOAD:", payload.decode('utf-8', errors='replace'))

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if data.get('event') == 'payment.success':
        txn_details = data.get('data', {})
        amount = Decimal(str(txn_details.get('amount', '0')))
        email = txn_details.get('customer', {}).get('email') if isinstance(txn_details.get('customer'), dict) else None
        reference = txn_details.get('reference')

        account_number = None
        if isinstance(txn_details.get('customer'), dict):
            account_number = txn_details['customer'].get('accountNumber') or txn_details['customer'].get('account_number')
        if not account_number and isinstance(txn_details.get('virtual_account'), dict):
            account_number = txn_details['virtual_account'].get('accountNumber') or txn_details['virtual_account'].get('account_number')
        if not account_number and isinstance(txn_details.get('beneficiary'), dict):
            account_number = txn_details['beneficiary'].get('account_number')
        if not account_number and isinstance(txn_details.get('recipient'), dict):
            account_number = txn_details['recipient'].get('account_number')

        if not Transaction.objects.filter(reference=reference).exists():
            user = None
            if email:
                user = User.objects.filter(email=email).first()
            if not user and account_number:
                user = User.objects.filter(profile__gafia_account_number=account_number).first()

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
                
                with open('/tmp/gafia_webhook.log', 'a') as f:
                    f.write(f"✅ CREDITED: {user.email} - ₦{amount}\n\n")
                
                return HttpResponse(status=200)
            else:
                with open('/tmp/gafia_webhook.log', 'a') as f:
                    f.write(f"❌ NO USER: email={email}, account={account_number}\n\n")
                print("GAFIA WEBHOOK: no user found for email/account_number", email, account_number)
                return HttpResponse(status=404)

    return HttpResponse(status=200)

# ====================== PURCHASE VIEWS ======================
@login_required
@csrf_exempt
def buy_airtime(request):
    if request.method == 'POST':
        try:
            form = AirtimeForm(request.POST)
            if form.is_valid():
                pin = form.cleaned_data.get('pin') or request.POST.get('pin')
                wallet = request.user.wallet
                amount = form.cleaned_data['amount']
                phone = form.cleaned_data['phone']
                network_name = form.cleaned_data['network'].upper()

                # 1. Security & Balance Checks
                if not wallet.pin:
                    return JsonResponse({'status': 'no_pin', 'message': "Create Transaction PIN first"}, status=400)
                if not wallet.check_pin(pin):
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
                    
                    # 🔥 CHANGE: Capture the transaction object in a variable
                    new_tx = Transaction.objects.create(
                        user=request.user,
                        transaction_type='Airtime',
                        amount=amount,
                        provider=network_name,
                        phone_or_meter=phone,
                        status='Successful',
                        transaction_id=result.get('transaction_id')
                    )
                    
                    # 🔥 CHANGE: Return the redirect_url for the receipt
                    return JsonResponse({
                        'status': 'success', 
                        'message': f'✅ ₦{amount} Airtime sent!',
                        'redirect_url': reverse('receipt_detail', kwargs={'pk': new_tx.pk})
                    })
                else:
                    return JsonResponse({'status': 'error', 'message': result['message']}, status=400)
            
            return JsonResponse({'status': 'error', 'message': '❌ Invalid form data'}, status=400)
        except Exception as e:
            print(f"Buy airtime exception: {traceback.format_exc()}")
            return JsonResponse({'status': 'error', 'message': f'Server error: {str(e)}'}, status=500)

    form = AirtimeForm()
    return render(request, 'vtuapp/buy_airtime.html', {'form': form})


@login_required
@csrf_exempt
def buy_data(request):
    if request.method == 'POST':
        try:

            form = DataPurchaseForm(request.POST)
            if not form.is_valid():
                return JsonResponse({'status': 'error', 'message': 'Please fill all fields correctly'}, status=400)

            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet
            plan = form.cleaned_data['plan']
            phone = form.cleaned_data['phone']

            print("=== BUY DATA DEBUG ===")
            print(f"Plan: {plan.name} | Price: {plan.price}")
            print(f"network_id: {plan.network_id} | smeplug_plan_id: {plan.smeplug_plan_id}")
            print(f"Phone: {phone}")

            # PIN Check
            if not wallet.pin:
                return JsonResponse({'status': 'no_pin', 'message': "Create Transaction PIN first"}, status=400)

            if not wallet.check_pin(pin):
                return JsonResponse({'status': 'error', 'message': '❌ Incorrect Transaction PIN'}, status=400)

            # Balance Check
            if wallet.balance < plan.price:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)

            # === API CALL ===
            service = VTUApiService()
            result = service.buy_data(
                network_id=plan.network_id,      # Correct parameter name
                plan_id=plan.smeplug_plan_id,
                phone=phone,
                amount=plan.price
            )

            print(f"API Result: {result}")

            if result['success']:
                wallet.balance -= plan.price
                wallet.save()
                
                # 🔥 CHANGE: Capture transaction object
                new_tx = Transaction.objects.create(
                    user=request.user,
                    transaction_type='Data',
                    amount=plan.price,
                    provider=plan.network.name if hasattr(plan, 'network') else 'smeplug',
                    phone_or_meter=phone,
                    status='Successful',
                    transaction_id=result.get('transaction_id')
                )

                # 🔥 CHANGE: Return redirect_url
                return JsonResponse({
                    'status': 'success',
                    'message': f'✅ {plan.name} purchased!',
                    'redirect_url': reverse('receipt_detail', kwargs={'pk': new_tx.pk})
                })
            else:
                # ... (error handling) ...
                return JsonResponse({'status': 'error', 'message': result.get('message')}, status=400)

        except Exception as e:
            # ... (exception handling) ...
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

