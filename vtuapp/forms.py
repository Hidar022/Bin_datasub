from django import forms
from .models import DataPlan


class AirtimeForm(forms.Form):
    NETWORK_CHOICES = [('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')]
    network = forms.ChoiceField(choices=NETWORK_CHOICES)
    phone = forms.CharField(max_length=11, widget=forms.TextInput(attrs={'placeholder': '08012345678'}))
    amount = forms.DecimalField(max_digits=6, decimal_places=2, min_value=50)

class DataForm(forms.Form):
    NETWORK_CHOICES = [('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')]
    network = forms.ChoiceField(choices=NETWORK_CHOICES)
    phone = forms.CharField(max_length=11)
    amount = forms.DecimalField(max_digits=6, decimal_places=2, min_value=100)

class ElectricityForm(forms.Form):
    provider = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'IKEJA Electric'}))
    meter_number = forms.CharField(max_length=20)
    amount = forms.DecimalField(max_digits=8, decimal_places=2, min_value=1000)

class CableTVForm(forms.Form):
    provider = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'DSTV / GOTV'}))
    smartcard_number = forms.CharField(max_length=20)
    amount = forms.DecimalField(max_digits=8, decimal_places=2, min_value=1000)

class DataPurchaseForm(forms.Form):
    network = forms.ChoiceField(choices=[
        ('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')
    ])
    plan = forms.ModelChoiceField(queryset=DataPlan.objects.filter(is_active=True), empty_label="Select a data plan")
    phone = forms.CharField(max_length=11, widget=forms.TextInput(attrs={'placeholder': '08012345678'}))
    pin = forms.CharField(max_length=4, widget=forms.PasswordInput(attrs={'placeholder': '••••'}))