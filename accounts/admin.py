from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from django import forms
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from .models import Account, Courier, CourierTrackingHistory
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from io import BytesIO
from email.mime.image import MIMEImage
import base64
import barcode
from barcode.writer import ImageWriter

INLINE_INPUT_STYLE = (
    "width:360px; padding:10px; border:1px solid #e5e7eb; "
    "border-radius:8px; outline:none; font-size:14px;"
)

# ----------------------
# ACCOUNT ADMIN
# ----------------------

class AccountCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        required=True,
        widget=forms.TextInput(attrs={
            "type": "password",
            "placeholder": "Enter password",
            "style": INLINE_INPUT_STYLE
        })
    )
    password2 = forms.CharField(
        label="Confirm Password",
        required=True,
        widget=forms.TextInput(attrs={
            "type": "password",
            "placeholder": "Confirm password",
            "style": INLINE_INPUT_STYLE
        })
    )

    class Meta:
        model = Account
        fields = ("email", "first_name", "last_name", "phone_number")
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "Email address", "style": INLINE_INPUT_STYLE}),
            "first_name": forms.TextInput(attrs={"placeholder": "First name", "style": INLINE_INPUT_STYLE}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name", "style": INLINE_INPUT_STYLE}),
            "phone_number": forms.TextInput(attrs={"placeholder": "Phone number", "style": INLINE_INPUT_STYLE}),
        }

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don’t match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])  # hashed password
        if commit:
            user.save()
        return user


class AccountChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Password (hashed)",
        help_text='Use the "Change password" form to update this.'
    )

    class Meta:
        model = Account
        fields = ("email", "first_name", "last_name", "phone_number", "password", "is_active", "is_staff", "is_superuser")


@admin.register(Account)
class AccountAdmin(ModelAdmin, BaseUserAdmin):
    add_form = AccountCreationForm
    form = AccountChangeForm
    model = Account

    list_display = ("email", "first_name", "last_name", "phone_number", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name", "phone_number")
    ordering = ("email",)

    fieldsets = (
        ("Personal Info", {"fields": ("email", "first_name", "last_name", "phone_number")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "phone_number", "password1", "password2", "is_active", "is_staff", "is_superuser"),
        }),
    )

    readonly_fields = ("last_login", "date_joined")



# ----------------------
# INLINE HISTORY IN COURIER ADMIN
# ----------------------

# class CourierTrackingHistoryInline(TabularInline):
#     model = CourierTrackingHistory
#     extra = 0
#     fields = ("status", "location_country", "location_city", "description", "timestamp")
#     ordering = ("-timestamp",)
#     readonly_fields = ("timestamp",)

# ----------------------
# COURIER ADMIN
# ----------------------
@admin.register(Courier)
class CourierAdmin(ModelAdmin):
    list_display = (
        "tracking_number", "status", "current_location_country", "current_location_city",
        "estimated_delivery_date"
    )
  
    list_filter = ("status", "receiver_country", "sender_country", "category")
    search_fields = (
        "tracking_number", "receiver_name", "receiver_email",
        "sender_name", "sender_email"
    )
    ordering = ("-created_at",)

    list_editable = (
        "status",
        "current_location_country",
        "current_location_city",
        "estimated_delivery_date",
    )

    fieldsets = (
        ("Tracking Information", {
            "fields": (
                "tracking_number", 
                "status", 
                "current_location_country", 
                "current_location_city",
                "trailer_number",
                "seal_number",
                "scac",
            )
        }),
        ("Receiver Details", {
            "fields": (
                "receiver_name", 
                "receiver_contact_number", 
                "receiver_email",
                "receiver_address", 
                "receiver_country", 
                "receiver_city"
            )
        }),
        ("Sender Details", {
            "fields": (
                "sender_name", 
                "sender_contact_number", 
                "sender_email",
                "sender_address", 
                "sender_country", 
                "sender_city"
            )
        }),
        ("Package Details", {
            "fields": (
                "item_description", 
                "number_of_items", 
                "parcel_colour",
                "weight", 
                "rate", 
                "category", 
                "destination_country", 
                "destination_city"
            )
        }),
        ("Timeline", {
            "fields": ("date_sent", "estimated_delivery_date")
        }),
    )

    readonly_fields = ("tracking_number", "created_at", "updated_at")

    actions = ['send_receipt_email']

    # -------------------------
    # Custom Admin Action
    # -------------------------
    def send_receipt_email(self, request, queryset):
        """
        Sends the waybill receipt as a fully styled HTML email with barcode image.
        """
        for courier in queryset:
            # Generate barcode as PNG image in memory
            CODE128 = barcode.get_barcode_class('code128')
            buffer = BytesIO()
            CODE128(courier.tracking_number, writer=ImageWriter()).write(buffer)

            # Create MIME image for inline embedding
            barcode_image = MIMEImage(buffer.getvalue())
            barcode_image.add_header('Content-ID', '<barcode_image>')
            barcode_image.add_header('Content-Disposition', 'inline', filename="barcode.png")

            # Render HTML template with cid reference
            html_message = render_to_string(
                'courier_receipt.html', 
                {
                    'courier': courier,
                    'barcode_cid': "cid:barcode_image"
                }
            )

            # Send HTML email
            email = EmailMessage(
                subject=f"Waybill Receipt - {courier.tracking_number}",
                body=html_message,
                to=[courier.receiver_email]
            )
            email.content_subtype = 'html'
            email.attach(barcode_image)  # attach barcode inline

            try:
                email.send()
                self.message_user(request, f"Receipt sent successfully to {courier.receiver_email}")
            except Exception as e:
                self.message_user(request, f"Failed to send to {courier.receiver_email}: {str(e)}", level='error')

    send_receipt_email.short_description = "Send Waybill Receipt to Receiver Email"

# ----------------------
# COURIER TRACKING HISTORY ADMIN
# ----------------------

@admin.register(CourierTrackingHistory)
class CourierTrackingHistoryAdmin(ModelAdmin):
    list_display = ("courier", "status", "location_country", "location_city", "timestamp")
    list_filter = ("status", "location_country")
    search_fields = ("courier__tracking_number", "location_city__name", "description")
    ordering = ("-timestamp",)


# ----------------------
# SIGNALS TO AUTO-CREATE HISTORY
# ----------------------

@receiver(post_save, sender=Courier)
def create_or_update_tracking_history(sender, instance, created, **kwargs):
    """Automatically log courier creation and updates to history."""
    if created:
        # New courier -> create initial history record
        CourierTrackingHistory.objects.create(
            courier=instance,
            status=instance.status,
            location_country=instance.current_location_country,
            location_city=instance.current_location_city,
            description="Courier created"
        )
    else:
        # On update, create a new history log if key fields changed
        last_history = CourierTrackingHistory.objects.filter(
            courier=instance
        ).order_by("-timestamp").first()

        if (
            not last_history
            or last_history.status != instance.status
            or last_history.location_country != instance.current_location_country
            or last_history.location_city != instance.current_location_city
            or last_history and instance.estimated_delivery_date
            and last_history.timestamp.date() != instance.estimated_delivery_date
        ):
            CourierTrackingHistory.objects.create(
                courier=instance,
                status=instance.status,
                location_country=instance.current_location_country,
                location_city=instance.current_location_city,
                description="Courier details updated"
            )