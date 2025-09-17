import random
import string
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from smart_selects.db_fields import ChainedForeignKey
from django_countries.fields import CountryField
from django.conf import settings
from django.utils import timezone



class AccountManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("User must have an email address")
        
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email.split('@')[0])  # Default username from email if not provided
        first_name = extra_fields.pop('first_name', '')
        last_name = extra_fields.pop('last_name', '')
        phone_number = extra_fields.pop('phone_number', '')

        user = self.model(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(email=email, password=password, **extra_fields)




class Account(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(verbose_name="Email", max_length=100, unique=True)
    username = models.CharField(max_length=100, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    date_joined = models.DateTimeField(verbose_name="Date Joined", auto_now_add=True)
    last_login = models.DateTimeField(verbose_name="Last Login", auto_now=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = AccountManager()

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return True


def generate_tracking_number():
    """Generate a unique tracking number like CTR-ABC123."""
    prefix = "CTR"
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{random_part}"


class Courier(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="couriers",
        null=True,
        blank=True,
    )

     # Shipping Document Details
    trailer_number = models.CharField(
        max_length=50,
        default='332764',
        help_text="Trailer Number"
    )
    seal_number = models.CharField(
        max_length=50,
        default='9977',
        help_text="Seal Number"
    )
    scac = models.CharField(
        max_length=50,
        default='N/A',
        blank=True,
        null=True,
        help_text="Standard Carrier Alpha Code (SCAC)"
    )

    # Tracking
    tracking_number = models.CharField(max_length=20, unique=True, editable=False)
    status = models.CharField(
        max_length=50,
        choices=[
            ("Order Placed", "Order Placed"),
            ("In Transit", "In Transit"),
            ("Out for Delivery", "Out for Delivery"),
            ("Delivered", "Delivered"),
            ("Pending", "Pending"),
            ("Returned", "Returned"),
            ("Failed Delivery", "Failed Delivery"),
        ],
        default="Pending",
    )
    current_location_country = CountryField(blank_label="Select Country", blank=True, null=True)
    current_location_city = models.CharField(max_length=100, blank=True, null=True)

    # Receiver
    receiver_name = models.CharField(max_length=255)
    receiver_contact_number = models.CharField(max_length=15)
    receiver_email = models.EmailField()
    receiver_address = models.TextField()
    receiver_country = CountryField(blank_label="Select Country", blank=True, null=True)
    receiver_city = models.CharField(max_length=100, blank=True, null=True)

    # Sender
    sender_name = models.CharField(max_length=255)
    sender_contact_number = models.CharField(max_length=15)
    sender_email = models.EmailField()
    sender_address = models.TextField()
    sender_country = CountryField(blank_label="Select Country", blank=True, null=True)
    sender_city = models.CharField(max_length=100, blank=True, null=True)

    # Package
    item_description = models.TextField()
    number_of_items = models.PositiveIntegerField(default=1)
    parcel_colour = models.CharField(max_length=50)
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    category = models.CharField(
        max_length=50,
        choices=[("Domestic", "Domestic"), ("International", "International")],
        default="Domestic",
    )
    destination_country = CountryField(blank_label="Select Country", blank=True, null=True)
    destination_city = models.CharField(max_length=100, blank=True, null=True)

    date_sent = models.DateField()
    estimated_delivery_date = models.DateField()

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            # keep regenerating until we find a unique one
            while True:
                new_tracking = generate_tracking_number()
                if not Courier.objects.filter(tracking_number=new_tracking).exists():
                    self.tracking_number = new_tracking
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tracking_number} - {self.status}"


class CourierTrackingHistory(models.Model):
    courier = models.ForeignKey(
        Courier,
        on_delete=models.CASCADE,
        related_name="tracking_history",
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ("Order Placed", "Order Placed"),
            ("In Transit", "In Transit"),
            ("Out for Delivery", "Out for Delivery"),
            ("Delivered", "Delivered"),
            ("Pending", "Pending"),
            ("Returned", "Returned"),
            ("Failed Delivery", "Failed Delivery"),
        ],
    )
    location_country = CountryField(blank_label="Select Country", blank=True, null=True)
    location_city = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(
        blank=True,
        help_text="Optional details (e.g. 'Departed Paris Airport' or 'Arrived at Lagos facility')",
    )
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.courier.tracking_number} - {self.status} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"