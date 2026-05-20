from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password, check_password

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    dob = models.DateField(blank=True, null=True)
    email_otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    gafia_account_number = models.CharField(max_length=15, null=True, blank=True)
    gafia_bank_name = models.CharField(max_length=50, null=True, blank=True)
    gafia_account_name = models.CharField(max_length=100, null=True, blank=True)
    transaction_pin = models.CharField(max_length=128, null=True, blank=True)  # ✅ NOW HASHED (up to 128 chars for hash)

    def __str__(self):
        return self.user.username
    
    def set_pin(self, raw_pin):
        """Hash the PIN before saving (use same method as Wallet)"""
        self.transaction_pin = make_password(raw_pin)
        self.save()
    
    def check_pin(self, raw_pin):
        """Check if entered PIN is correct"""
        if not self.transaction_pin:
            return False
        return check_password(raw_pin, self.transaction_pin)

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
    transaction_type = models.CharField(max_length=50) 
    amount = models.DecimalField(max_digits=10, decimal_places=2) # What User paid
    
    # --- ADD THIS FIELD ---
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # What SMEPlug charged you
    
    provider = models.CharField(max_length=100, blank=True)
    phone_or_meter = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, default='Successful')
    reference = models.CharField(max_length=100, blank=True, null=True, unique=True) 
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} - ₦{self.amount}"

    @property
    def profit(self):
        # We only calculate profit on service sales, not funding
        if self.transaction_type in ['Data Purchase', 'Airtime Purchase']:
            return self.amount - self.cost_price
        return 0

class DataPlan(models.Model):
    PLAN_TYPES = [
        ('SME', 'SME'),
        ('GIFTING', 'Gifting'),
        ('AWOOF', 'Awoof / Promo'),
        ('CORPORATE', 'Corporate Gifting'),
    ]
                                                                                                                                                   
    network = models.CharField(max_length=20, choices=[
        ('MTN', 'MTN'), 
        ('Glo', 'Glo'), 
        ('Airtel', 'Airtel'), 
        ('9mobile', '9mobile')
    ])
    name = models.CharField(max_length=100)
    # 🚀 NEW FIELD: Categorization system
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES, default='SME')
    data_amount = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    validity = models.CharField(max_length=50, default="30 Days")
    is_active = models.BooleanField(default=True)

    # ==================== NEW FIELDS FOR API ====================
    network_id = models.IntegerField(default=1, help_text="1=MTN, 2=Airtel, 3=9mobile, 4=Glo")
    smeplug_plan_id = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        help_text="Plan ID from Smeplug (e.g: 1, AIR1000, 9MOB500)"
    )

    def __str__(self):
        return f"{self.network} - {self.name} ({self.get_plan_type_display()}) - ₦{self.price}"

class BiometricCredential(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='biometric_credentials')
    credential_id = models.TextField() 
    public_key = models.TextField()
    sign_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Biometric for {self.user.username}"

# --- Signals

@receiver(post_save, sender=User)
def create_user_assets(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        Wallet.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_assets(sender, instance, **kwargs):
    Profile.objects.get_or_create(user=instance)
    Wallet.objects.get_or_create(user=instance)

    instance.profile.save()
    instance.wallet.save()
