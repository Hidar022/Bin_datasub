from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.conf import settings
from decimal import Decimal
import time
import requests
import json
from django.views.decorators.csrf import csrf_exempt

# Models
from .models import Wallet, Transaction, DataPlan, Profile

# Forms
from .forms import (
    AirtimeForm, DataForm, ElectricityForm, CableTVForm, 
    DataPurchaseForm
)

from django.contrib.auth.hashers import check_password, make_password


def home_redirect(request):
    return redirect('login') if not request.user.is_authenticated else redirect('dashboard')


# ====================== AUTH ======================
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'vtuapp/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'vtuapp/login.html', {'form': form})


def logout_view(request):
    logout(request)
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

            return JsonResponse({'status': 'success', 'message': '✅ Profile updated successfully!'})

        elif section == 'password':
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if not check_password(old_password, request.user.password):
                return JsonResponse({'status': 'error', 'message': '❌ Current password is incorrect'})
            elif new_password != confirm_password:
                return JsonResponse({'status': 'error', 'message': '❌ New passwords do not match'})
            elif len(new_password) < 6:
                return JsonResponse({'status': 'error', 'message': '❌ Password must be at least 6 characters'})
            else:
                request.user.set_password(new_password)
                request.user.save()
                return JsonResponse({'status': 'success', 'message': '✅ Account password updated successfully!'})

        elif section == 'pin':
            old_pin = request.POST.get('old_pin')
            new_pin = request.POST.get('new_pin')

            wallet = request.user.wallet
            if not wallet.check_pin(old_pin):
                return JsonResponse({'status': 'error', 'message': '❌ Current PIN is incorrect'})
            elif len(new_pin) != 4 or not new_pin.isdigit():
                return JsonResponse({'status': 'error', 'message': '❌ New PIN must be exactly 4 digits'})
            else:
                wallet.set_pin(new_pin)
                return JsonResponse({'status': 'success', 'message': '✅ Transaction PIN updated successfully!'})

        return JsonResponse({'status': 'error', 'message': 'Invalid section'})

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
def buy_airtime(request):
    if request.method == 'POST':
        form = AirtimeForm(request.POST)
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
                    transaction_type='Airtime',
                    amount=amount,
                    provider=form.cleaned_data['network'],
                    phone_or_meter=form.cleaned_data['phone'],
                    status='Successful'
                )
                return JsonResponse({
                    'status': 'success',
                    'message': f'✅ ₦{amount} Airtime sent successfully!'
                })
            else:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)
        
        return JsonResponse({'status': 'error', 'message': '❌ Please fill all fields correctly'}, status=400)

    form = AirtimeForm()
    return render(request, 'vtuapp/buy_airtime.html', {'form': form})


@login_required
def buy_data(request):
    if request.method == 'POST':
        form = DataPurchaseForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet

            if not wallet.check_pin(pin):
                return JsonResponse({'status': 'error', 'message': '❌ Incorrect Transaction PIN'}, status=400)

            plan = form.cleaned_data['plan']
            amount = plan.price

            if wallet.balance >= amount:
                wallet.balance -= amount
                wallet.save()

                Transaction.objects.create(
                    user=request.user,
                    transaction_type='Data',
                    amount=amount,
                    provider=plan.network,
                    phone_or_meter=form.cleaned_data['phone'],
                    status='Successful'
                )
                return JsonResponse({
                    'status': 'success',
                    'message': f'✅ {plan.name} purchased successfully!'
                })
            else:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)

        return JsonResponse({'status': 'error', 'message': '❌ Please fill all fields correctly'}, status=400)

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
@login_required
def webauthn_register_options(request):
    """Generate registration options for fingerprint/face ID"""
    try:
        options = generate_registration_options(
            rp_id=request.get_host().split(':')[0],
            rp_name="Bin Datasub",
            user_id=str(request.user.id).encode(),
            user_name=request.user.username,
            user_display_name=request.user.username,
        )

        webauthn_challenges[request.user.id] = options.challenge

        return JsonResponse(options_to_json(options))
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@csrf_exempt
@login_required
def webauthn_register_complete(request):
    """Verify and save the biometric credential"""
    try:
        data = json.loads(request.body)
        challenge = webauthn_challenges.get(request.user.id)

        if not challenge:
            return JsonResponse({'status': 'error', 'message': 'Challenge expired'}, status=400)

        verification = verify_registration_response(
            credential=data,
            expected_challenge=challenge,
            expected_rp_id=request.get_host().split(':')[0],
            expected_origin=request.build_absolute_uri('/'),
        )

        # Save credential (for now just success message)
        messages.success(request, '✅ Fingerprint / Face ID registered successfully!')
        webauthn_challenges.pop(request.user.id, None)

        return JsonResponse({'status': 'success', 'message': 'Biometric registered successfully!'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# Temporary storage for challenges
webauthn_challenges = {}