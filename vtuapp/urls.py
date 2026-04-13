from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Services
    path('buy-airtime/', views.buy_airtime, name='buy_airtime'),
    path('buy-data/', views.buy_data, name='buy_data'),
    path('pay-electricity/', views.pay_electricity, name='pay_electricity'),
    path('cable-tv/', views.cable_tv, name='cable_tv'),
    
    # New pages
    path('fund-wallet/', views.fund_wallet, name='fund_wallet'),
    path('transactions/', views.transactions_history, name='transactions'),
    path('services/', views.services_page, name='services'),
    path('support/', views.support, name='support'),
    path('referral/', views.referral, name='referral'),
    path('fund-wallet/callback/', views.fund_wallet_callback, name='fund_wallet_callback'),
    path('settings/', views.settings_page, name='settings'),

    # 1. Page to enter email
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(template_name='vtuapp/password_reset.html'), 
         name='password_reset'),
    
    # 2. Success message after email is sent
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='vtuapp/password_reset_done.html'), 
         name='password_reset_done'),
    
    # 3. The link user clicks in their email
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='vtuapp/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    
    # 4. Final success message
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='vtuapp/password_reset_complete.html'), 
         name='password_reset_complete'),

    path('', views.home_redirect, name='home'),
]