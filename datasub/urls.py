"""
URL configuration for datasub project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from vtuapp import views as vtuapp_views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('fund-wallet/callback/', vtuapp_views.fund_wallet_callback, name='fund_wallet_callback'),
    path('gafia-webhook/', vtuapp_views.gafiapay_webhook, name='gafia_webhook'),
    path('gafiapay-webhook/', vtuapp_views.gafiapay_webhook, name='gafiapay_webhook'),
    path('', include('vtuapp.urls')),
]

