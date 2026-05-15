from django import forms
from .models import DataPlan
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

# ✅ SECURITY: Phone number validator
phone_validator = RegexValidator(
    r'^0[789]\d{8}$',
    'Please enter a valid Nigerian phone number (e.g., 08012345678)'
)

class AirtimeForm(forms.Form):
    NETWORK_CHOICES = [('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')]
    network = forms.ChoiceField(choices=NETWORK_CHOICES)
    phone = forms.CharField(
        max_length=11, 
        validators=[phone_validator],
        widget=forms.TextInput(attrs={'placeholder': '08012345678'})
    )
    amount = forms.DecimalField(max_digits=6, decimal_places=2, min_value=50)
    pin = forms.CharField(max_length=4, widget=forms.PasswordInput(attrs={'placeholder': '••••'}))

class DataForm(forms.Form):
    NETWORK_CHOICES = [('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')]
    network = forms.ChoiceField(choices=NETWORK_CHOICES)
    phone = forms.CharField(
        max_length=11,
        validators=[phone_validator]
    )
    amount = forms.DecimalField(max_digits=6, decimal_places=2, min_value=100)

class ElectricityForm(forms.Form):
    provider = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'IKEJA Electric'}))
    meter_number = forms.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\d{10,12}$', 'Invalid meter number')]
    )
    amount = forms.DecimalField(max_digits=8, decimal_places=2, min_value=1000)
    pin = forms.CharField(max_length=4, widget=forms.PasswordInput(attrs={'placeholder': '••••'}))

class CableTVForm(forms.Form):
    provider = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'DSTV / GOTV'}))
    smartcard_number = forms.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\d{10,20}$', 'Invalid smart card number')]
    )
    amount = forms.DecimalField(max_digits=8, decimal_places=2, min_value=1000)
    pin = forms.CharField(max_length=4, widget=forms.PasswordInput(attrs={'placeholder': '••••'}))

class DataPurchaseForm(forms.Form):
    network = forms.ChoiceField(choices=[
        ('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')
    ])
    plan = forms.ModelChoiceField(queryset=DataPlan.objects.filter(is_active=True), empty_label="Select a data plan")
    phone = forms.CharField(
        max_length=11, 
        validators=[phone_validator],
        widget=forms.TextInput(attrs={'placeholder': '08012345678'})
    )
    pin = forms.CharField(max_length=4, widget=forms.PasswordInput(attrs={'placeholder': '••••'}))

# --- AUTH FORMS ---
class CustomUserCreationForm(UserCreationForm):
    full_name = forms.CharField(
        max_length=150, # Changed from max_digits to max_length
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your full name',
            'autofocus': 'autofocus'
        }),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'aliyu@example.com'})
    )
    phone_number = forms.CharField(
        max_length=11,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': '08012345678',
            'class': 'phone-field',
            'inputmode': 'numeric'
        })
    )

    class Meta:
        model = User
        # Include fields used by the default User model
        fields = ['full_name', 'username', 'email', 'phone_number']
    
    # This ensures the {% for field in form %} loop follows this exact order
    field_order = ['full_name', 'username', 'email', 'phone_number', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'placeholder': 'Choose a username'})
        
        if 'password1' in self.fields:
            self.fields['password1'].widget.attrs.update({'placeholder': 'Create password'})
        if 'password2' in self.fields:
            self.fields['password2'].widget.attrs.update({'placeholder': 'Confirm password'})

    def save(self, commit=True):
        user = super().save(commit=False)
        # Storing full_name in first_name for compatibility
        user.first_name = self.cleaned_data["full_name"]
        # Note: If your User model doesn't have a 'phone_number' field, 
        # you'll need a Profile model or a Custom User Model to save this.
        if commit:
            user.save()
        return user

class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'placeholder': 'Your username'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'placeholder': '••••••••'
    }))