from django.urls import path
from . import views

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
    path('profile/', views.profile, name='profile'),
    path('support/', views.support, name='support'),
    path('referral/', views.referral, name='referral'),
    path('fund-wallet/callback/', views.fund_wallet_callback, name='fund_wallet_callback'),
    path('', views.home_redirect, name='home'),
]