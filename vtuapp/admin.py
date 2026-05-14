from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import path
from .views import admin_dashboard
from .models import Profile, Transaction, Wallet, DataPlan

class CustomAdminSite(admin.AdminSite):
    site_header = "Bin Datasub Admin"
    site_title = "Bin Datasub Admin Portal"
    index_title = "System Overview"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_view(admin_dashboard), name='index'),
        ]
        return custom_urls + urls

admin_site = CustomAdminSite(name='custom_admin')
admin_site.register(User, admin.ModelAdmin)
admin_site.register(Profile, admin.ModelAdmin)
admin_site.register(Transaction, admin.ModelAdmin)
admin_site.register(Wallet, admin.ModelAdmin)
admin_site.register(DataPlan, admin.ModelAdmin)
