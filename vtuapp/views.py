import requests # Add this to your imports at the top
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Wallet, Transaction
from .forms import AirtimeForm, DataForm, ElectricityForm, CableTVForm
from .forms import DataPurchaseForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from .models import Wallet, Transaction, DataPlan
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from decimal import Decimal
import time

from pypaystack2 import Paystack

def home_redirect(request):
    return redirect('login') if not request.user.is_authenticated else redirect('dashboard')

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            if User.objects.filter(username=username).exists():
                messages.error(request, "This username is already taken. Please choose another.")
            else:
                user = form.save()
                login(request, user)
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

@login_required
def dashboard(request):
    wallet = request.user.wallet
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')[:4]
    return render(request, 'vtuapp/dashboard.html', {
        'wallet': wallet,
        'transactions': transactions
    })

# ==================== INTERACTIVE SERVICE VIEWS ====================

@login_required
def buy_data(request):
    if request.method == 'POST':
        form = DataPurchaseForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet

            if not wallet.pin or wallet.pin != pin:
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
                    'message': f'✅ {plan.name} ({plan.data_amount}) purchased successfully!'
                })
            else:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)

        return JsonResponse({'status': 'error', 'message': '❌ Please fill all fields correctly'}, status=400)

    # GET request - send plans to template
    form = DataPurchaseForm()
    plans = DataPlan.objects.filter(is_active=True)
    
    return render(request, 'vtuapp/buy_data.html', {
        'form': form,
        'plans': plans
    })

@login_required
def pay_electricity(request):
    if request.method == 'POST':
        form = ElectricityForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet

            if not wallet.pin or wallet.pin != pin:
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

            if not wallet.pin or wallet.pin != pin:
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


# ====================== FUND WALLET ======================

@login_required
def fund_wallet(request):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        email = request.user.email or f"{request.user.username}@bindatasub.com"
        
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "amount": int(amount) * 100,
            "email": email,
            "callback_url": request.build_absolute_uri('/fund-wallet/callback/')
        }

        response = requests.post(url, headers=headers, json=data)
        res_data = response.json()

        if res_data['status']:
            return redirect(res_data['data']['authorization_url'])
        else:
            messages.error(request, "Paystack error: " + res_data['message'])
            return redirect('fund_wallet')
            
    return render(request, 'vtuapp/fund_wallet.html')

# ====================== PAYSTACK CALLBACK ======================
@login_required
def fund_wallet_callback(request):
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, 'Payment reference not found')
        return redirect('dashboard')

    try:
        # Use requests to verify the payment directly with Paystack API
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        }
        
        response = requests.get(url, headers=headers)
        res_data = response.json()

        if res_data['status'] and res_data['data']['status'] == 'success':
            # Paystack sends amount in kobo (e.g., 10000 for ₦100)
            amount = Decimal(res_data['data']['amount']) / 100

            # Update the user's wallet
            wallet = request.user.wallet
            wallet.balance += amount
            wallet.save()

            # Record the transaction
            Transaction.objects.create(
                user=request.user,
                transaction_type='Wallet Funding',
                amount=amount,
                provider='Paystack',
                status='Successful'
            )

            messages.success(request, f'✅ ₦{amount:,.2f} has been credited to your wallet!')
        else:
            messages.error(request, 'Payment verification failed. Please contact support.')

    except Exception as e:
        messages.error(request, f'Verification error: {str(e)}')

    return redirect('dashboard')

@login_required
def transactions_history(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-timestamp')
    return render(request, 'vtuapp/transactions.html', {'transactions': transactions})

@login_required
def services_page(request):
    return render(request, 'vtuapp/services.html')

@login_required
def profile(request):
    if request.method == 'POST':
        pin = request.POST.get('pin')
        if pin and len(pin) == 4 and pin.isdigit():
            wallet = request.user.wallet
            wallet.pin = pin
            wallet.save()
            messages.success(request, '✅ 4-Digit PIN set successfully!')
            return redirect('profile')
        else:
            messages.error(request, 'PIN must be exactly 4 digits')
    
    return render(request, 'vtuapp/profile.html')

# Update all purchase views to require PIN (example for buy_airtime)
@login_required
def buy_airtime(request):
    if request.method == 'POST':
        form = AirtimeForm(request.POST)
        if form.is_valid():
            pin = form.cleaned_data.get('pin') or request.POST.get('pin')
            wallet = request.user.wallet

            if not wallet.pin or wallet.pin != pin:
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
                    'message': f'✅ ₦{amount} Airtime sent successfully to {form.cleaned_data["phone"]}'
                })
            else:
                return JsonResponse({'status': 'error', 'message': '❌ Insufficient wallet balance!'}, status=400)
        
        return JsonResponse({'status': 'error', 'message': '❌ Please fill all fields correctly'}, status=400)

    form = AirtimeForm()
    return render(request, 'vtuapp/buy_airtime.html', {'form': form})

@login_required
def support(request):
    if request.method == 'POST':
        # For now, just show success message (you can connect to email later)
        messages.success(request, '✅ Your message has been sent to our support team. We will reply soon!')
        return redirect('support')
    
    return render(request, 'vtuapp/support.html')   

@login_required
def referral(request):
    # You can generate a real referral code later
    referral_code = f"BDS-{request.user.username.upper()[:6]}"
    referral_link = f"https://yourdomain.com/register/?ref={referral_code}"
    
    return render(request, 'vtuapp/referral.html', {
        'referral_code': referral_code,
        'referral_link': referral_link
    })     