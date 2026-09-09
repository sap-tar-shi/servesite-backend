from django.core.management.base import BaseCommand
from billing.models import Plan
from billing.razorpay_client import create_plan


class Command(BaseCommand):
    help = "Create a Razorpay-side Plan for every local Plan missing a razorpay_plan_id (idempotent)."

    def handle(self, *args, **options):
        for plan in Plan.objects.filter(razorpay_plan_id="", is_active=True):
            data = create_plan(
                period=plan.billing_interval,
                interval=1,
                item_name=plan.name,
                amount_paise=int(plan.price * 100),
            )
            plan.razorpay_plan_id = data["id"]
            plan.save(update_fields=["razorpay_plan_id"])
            self.stdout.write(self.style.SUCCESS(f"Linked {plan.name} -> {data['id']}"))