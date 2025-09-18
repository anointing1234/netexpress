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
from xhtml2pdf import pisa
from barcode.writer import ImageWriter
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives

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
    readonly_fields = ("tracking_number", "created_at", "updated_at")
    actions = ['send_receipt_email']

    def send_receipt_email(self, request, queryset):
        """
        Sends a short professional email with a PDF receipt attachment.
        """
        for courier in queryset:
            # 1️⃣ Generate barcode image
            CODE128 = barcode.get_barcode_class('code128')
            buffer = BytesIO()
            CODE128(courier.tracking_number, writer=ImageWriter()).write(buffer)
            filename = f"barcodes/{courier.tracking_number}.png"
            file_path = default_storage.save(filename, ContentFile(buffer.getvalue()))
            barcode_url = request.build_absolute_uri(default_storage.url(file_path))

            # 2️⃣ Email message (short, professional)
            text_message = f"""
Dear {courier.receiver_name or 'Customer'},

Your shipment with Tracking ID: {courier.tracking_number} has been processed successfully.

You can track it online:
https://netexpressc.com/tracking/?tracking_id={courier.tracking_number}

Please here is  your official PDF receipt attached.

Thank you for choosing NetExpress.
            """

            email = EmailMultiAlternatives(
                subject=f"Your Shipment Receipt - {courier.tracking_number}",
                body=text_message,
                to=[courier.receiver_email],
            )

            # 3️⃣ Render HTML receipt for PDF
            pdf_html = render_to_string(
                "courier_receipt.html",
                {"courier": courier, "barcode_url": barcode_url}
            )

            # 4️⃣ Convert HTML to PDF
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(pdf_html, dest=pdf_buffer, encoding='utf-8')

            if pisa_status.err:
                self.message_user(
                    request,
                    f"Failed to generate PDF for {courier.tracking_number}.",
                    level="error"
                )
                continue

            pdf_buffer.seek(0)
            email.attach(
                f"Receipt_{courier.tracking_number}.pdf",
                pdf_buffer.read(),
                "application/pdf"
            )

            # 5️⃣ Send email
            try:
                email.send()
                self.message_user(
                    request,
                    f"Receipt sent successfully to {courier.receiver_email}"
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Failed to send to {courier.receiver_email}: {str(e)}",
                    level="error"
                )

    send_receipt_email.short_description = "Send PDF Receipt to Receiver Email"
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