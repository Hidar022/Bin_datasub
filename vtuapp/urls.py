from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
     path('', views.home, name='index'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # OTP Verification (New)
    path('verify-otp/', views.verify_otp, name='verify_otp'),

    # Services
    path('buy-airtime/', views.buy_airtime, name='buy_airtime'),
    path('buy-data/', views.buy_data, name='buy_data'),
    path('pay-electricity/', views.pay_electricity, name='pay_electricity'),
    path('cable-tv/', views.cable_tv, name='cable_tv'),
    
    # Wallet & Transactions
    path('fund-wallet/', views.fund_wallet, name='fund_wallet'),
    path('fund-wallet/callback/', views.fund_wallet_callback, name='fund_wallet_callback'),
    path('transactions/', views.transactions_history, name='transactions'),
    path('receipt/<int:pk>/', views.transaction_receipt, name='receipt_detail'),
    
    # Other pages
    path('services/', views.services_page, name='services'),
    path('support/', views.support, name='support'),
    path('referral/', views.referral, name='referral'),
    path('settings/', views.settings_page, name='settings'),

    # Forgot Password (Django built-in)
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(template_name='vtuapp/password_reset.html'), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='vtuapp/password_reset_done.html'), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='vtuapp/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='vtuapp/password_reset_complete.html'), 
         name='password_reset_complete'),

    # WebAuthn Biometric Routes (optional - you can keep or remove later)
    path('webauthn/register/', views.webauthn_register_options, name='webauthn_register_options'),
    path('webauthn/register/complete/', views.webauthn_register_complete, name='webauthn_register_complete'),

    # Root
    path('', views.home_redirect, name='home'),
]