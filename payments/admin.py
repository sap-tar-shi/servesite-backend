from django.contrib import admin
from .models import RazorpayConnection


@admin.register(RazorpayConnection)
class RazorpayConnectionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "razorpay_account_id", "is_active", "connected_at")
    readonly_fields = ("access_token_encrypted", "refresh_token_encrypted")