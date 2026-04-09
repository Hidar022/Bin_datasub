from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.user.username}'s Wallet - ₦{self.balance}"

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=50)      # Airtime, Data, Electricity, Cable TV
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.CharField(max_length=100, blank=True)
    phone_or_meter = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, default='Successful')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - ₦{self.amount}"

@receiver(post_save, sender=User)
def create_wallet(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.create(user=instance)

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pin = models.CharField(max_length=4, blank=True, null=True)   # New: 4-digit PIN

    def __str__(self):
        return f"{self.user.username}'s Wallet"

class DataPlan(models.Model):
    network = models.CharField(max_length=20, choices=[
        ('MTN', 'MTN'), ('Glo', 'Glo'), ('Airtel', 'Airtel'), ('9mobile', '9mobile')
    ])
    name = models.CharField(max_length=100)          # e.g. "1.5GB Daily", "10GB Monthly"
    data_amount = models.CharField(max_length=50)    # e.g. "1.5GB"
    price = models.DecimalField(max_digits=10, decimal_places=2)
    validity = models.CharField(max_length=50, default="30 Days")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.network} - {self.name} - ₦{self.price}"