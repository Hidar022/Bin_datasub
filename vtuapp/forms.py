from django import forms
from .models import DataPlan
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


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


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full bg-[#1a1a4a] border border-purple-500/50 focus:border-cyan-400 rounded-3xl px-6 py-5 text-white placeholder-gray-400 text-base outline-none transition-all'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'w-full bg-[#1a1a4a] border border-purple-500/50 focus:border-cyan-400 rounded-3xl px-6 py-5 text-white placeholder-gray-400 text-base outline-none transition-all'
            })

    # REMOVED the strict clean_email — we handle it in the view now
    # def clean_email(self): ...   ← Delete this method completely