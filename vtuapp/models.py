from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password, check_password

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    dob = models.DateField(blank=True, null=True)
    email_otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.user.username

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pin = models.CharField(max_length=128, blank=True, null=True)

    def set_pin(self, raw_pin):
        """Hash the PIN before saving"""
        self.pin = make_password(raw_pin)
        self.save()

    def check_pin(self, raw_pin):
        """Check if entered PIN is correct"""
        if not self.pin:
            return False
        return check_password(raw_pin, self.pin)

    def __str__(self):
        return f"{self.user.username}'s Wallet - ₦{self.balance}"

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=50) # Airtime, Data, etc.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.CharField(max_length=100, blank=True)
    phone_or_meter = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, default='Successful')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - ₦{self.amount}"

class DataPlan(models.Model):
    network = models.CharField(max_length=20, choices=[
        ('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')
    ])
    name = models.CharField(max_length=100)
    data_amount = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    validity = models.CharField(max_length=50, default="30 Days")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.network} - {self.name} - ₦{self.price}"

class BiometricCredential(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biometric_credentials')
    credential_id = models.TextField() 
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Biometric for {self.user.username}"

# --- Signals ---

@receiver(post_save, sender=User)
def create_user_assets(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        Wallet.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_assets(sender, instance, **kwargs):
    instance.profile.save()
    instance.wallet.save()