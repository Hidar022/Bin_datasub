# 1. Standard Library Imports
import json
import random
import traceback
import requests
from decimal import Decimal
from datetime import timedelta

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
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 30px; background: #0a0a2e; color: white; border-radius: 16px;">
                        <h2 style="color: #a855f7;">Bin Datasub</h2>
                        <p>Hi {existing_user.username},</p>
                        <p>Your verification code is:</p>
                        <div style="background:#1a1a4a; padding:25px; text-align:center; font-size:42px; letter-spacing:8px; border-radius:12px; margin:20px 0;">
                            <strong>{otp}</strong>
                        </div>
                        <p>This code expires in 10 minutes.</p>
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
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 30px; background: #0a0a2e; color: white; border-radius: 16px;">
                <h2 style="color: #a855f7;">Welcome to Bin Datasub</h2>
                <p>Hi {user.username},</p>
                <p>Your verification code is:</p>
                <div style="background:#1a1a4a; padding:25px; text-align:center; font-size:42px; letter-spacing:8px; border-radius:12px; margin:20px 0;">
                    <strong>{otp}</strong>
                </div>
                <p>This code expires in 10 minutes.</p>
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
            
            if not user.is_active:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': '❌ Please verify your email before logging in.'
                    }, status=400)
                else:
                    messages.error(request, 'Please verify your email before logging in.')
                    return redirect('login')

            login(request, user)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Login successful!'
                })
            else:
                messages.success(request, 'Login successful!')
                return redirect('dashboard')

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
    wallet = request.user.wallet
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
@login_required
def fund_wallet(request):
    if request.method == 'POST':
        try:
            amount = int(request.POST.get('amount'))
            if amount < 100:
                messages.error(request, 'Minimum funding amount is ₦100')
                return redirect('fund_wallet')

            url = "https://api.paystack.co/transaction/initialize"
            headers = {
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json",
            }
            data = {
                "amount": amount * 100,
                "email": request.user.email or f"{request.user.username}@bindatasub.com",
                "callback_url": request.build_absolute_uri('/fund-wallet/callback/')
            }

            response = requests.post(url, headers=headers, json=data)
            res_data = response.json()

            if res_data.get('status'):
                return redirect(res_data['data']['authorization_url'])
            else:
                messages.error(request, "Paystack error: " + res_data.get('message', 'Unknown error'))
                return redirect('fund_wallet')

        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            return redirect('fund_wallet')

    return render(request, 'vtuapp/fund_wallet.html')


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

