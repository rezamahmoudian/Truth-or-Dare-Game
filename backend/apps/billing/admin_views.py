"""Staff reports and two-step support forms; mutations remain in support.py."""
import logging
from datetime import timedelta
from urllib.parse import urlencode
from uuid import uuid4

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from apps.core.errors import DomainError
from .models import (Entitlement, Order, PaymentCheckout, SupportOperation,
                     VIPSubscription, Wallet, WalletLedger)
from .support import ACTIONS, execute, require_permission

logger = logging.getLogger("ft.billing")
CONFIRM_SALT = "billing.admin.support.v1"


def support_url(action="grant", target=""):
    return reverse("admin:billing_order_support") + "?" + urlencode({"action": action, "target": str(target)})


class SupportForm(forms.Form):
    action = forms.CharField(widget=forms.HiddenInput)
    target = forms.CharField(label="هدف عملیات", max_length=150)
    amount = forms.IntegerField(label="تعداد درخواست ویژه", min_value=1, max_value=1000000)
    reason = forms.CharField(label="دلیل رسیدگی", max_length=240,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "مثلاً جبران اختلال؛ شماره پرونده پشتیبانی…"}))
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, action, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target"].label = ACTIONS[action][2]
        if action not in ("grant", "debit"):
            self.fields.pop("amount")


def preview_target(action, target):
    """Resolve identity for the confirmation without creating wallets or grants."""
    try:
        if action == "grant":
            user = get_user_model().objects.get(username=target)
            wallet = Wallet.objects.filter(user=user).first()
            details = f"موجودی ثبت‌شده: {wallet.balance if wallet else 0} درخواست"
        elif action == "debit":
            obj = Entitlement.objects.select_related("wallet__user").get(pk=target)
            user = obj.wallet.user
            details = f"اعتبار #{obj.pk} · {obj.get_status_display()} · باقیمانده {obj.remaining} · رزرو {obj.reserved}"
        elif action == "revoke_vip":
            obj = VIPSubscription.objects.select_related("user").get(pk=target)
            user = obj.user
            details = f"دوره #{obj.pk} · از {timezone.localtime(obj.starts_at):%Y-%m-%d} تا {timezone.localtime(obj.ends_at):%Y-%m-%d}"
        elif action == "retry_delivery":
            obj = Order.objects.select_related("user").get(pk=target)
            user = obj.user
            details = f"{obj.product_snapshot.get('title', '')} · {obj.amount} ریال · {obj.get_status_display()}"
        else:
            obj = PaymentCheckout.objects.select_related("attempt__order__user").get(pk=target)
            user = obj.attempt.order.user
            details = f"{obj.attempt.provider} · {obj.last_code} · استعلام فقط از شناسهٔ ثبت‌شده درگاه"
        return user, details
    except (get_user_model().DoesNotExist, Entitlement.DoesNotExist, VIPSubscription.DoesNotExist,
            Order.DoesNotExist, PaymentCheckout.DoesNotExist, ValueError, ValidationError, OverflowError):
        raise DomainError("not_found", "کاربر یا رکورد مالی پیدا نشد.", 404) from None


def support_view(site, request):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    permitted = [(key, info) for key, info in ACTIONS.items() if request.user.has_perm(info[1])]
    if not permitted:
        raise PermissionDenied
    if request.method == "POST" and "confirmation" in request.POST:
        try:
            data = signing.loads(request.POST["confirmation"], salt=CONFIRM_SALT, max_age=900)
            if data.pop("actor_id") != request.user.pk:
                raise PermissionDenied
            op = execute(actor=request.user, **data)
            messages.success(request, f"{ACTIONS[op.action][0]} ثبت شد. شماره رسید: {op.pk}")
            return redirect(support_url(op.action))
        except (signing.BadSignature, KeyError):
            messages.error(request, "پیش‌نمایش معتبر نیست یا زمان آن گذشته؛ فرم را دوباره بررسی کن.")
            return redirect(support_url(permitted[0][0]))
        except DomainError as exc:
            if exc.status == 403:
                raise PermissionDenied from exc
            messages.error(request, exc.message)
            return redirect(support_url(data["action"], data["target"]))
        except PermissionDenied:
            raise
        except Exception:
            logger.exception("billing.support_failed")
            # Preserve the same signed operation for a safe retry after an unknown result.
            return TemplateResponse(request, "admin/billing/support_retry.html", {
                **site.each_context(request), "title": "عملیات تکمیل نشد",
                "confirmation": request.POST["confirmation"],
            }, status=503)
    action = (request.POST if request.method == "POST" else request.GET).get("action", permitted[0][0])
    if action not in ACTIONS:
        raise Http404
    try:
        require_permission(request.user, action)
    except DomainError as exc:
        raise PermissionDenied from exc
    form = SupportForm(request.POST if request.method == "POST" else None, action=action,
        initial={"action": action, "target": request.GET.get("target", ""), "idempotency_key": uuid4()})
    preview = confirmation = None
    if request.method == "POST" and form.is_valid():
        try:
            user, details = preview_target(action, form.cleaned_data["target"])
            data = {**form.cleaned_data, "idempotency_key": str(form.cleaned_data["idempotency_key"]),
                    "actor_id": request.user.pk, "expected_user_id": user.pk}
            confirmation = signing.dumps(data, salt=CONFIRM_SALT)
            preview = {"username": user.username, "name": user.display_name, "details": details,
                       "amount": data.get("amount"), "reason": data["reason"]}
        except DomainError as exc:
            form.add_error("target", exc.message)
    history = SupportOperation.objects.select_related("wallet__user", "actor")
    if not request.user.has_perm("billing.view_supportoperation"):
        history = history.filter(actor=request.user)
    recent = list(history[:20])
    for row in recent:
        row.action_label = ACTIONS.get(row.action, (row.action,))[0]
    return TemplateResponse(request, "admin/billing/support.html", {
        **site.each_context(request), "title": "عملیات پشتیبانی مالی", "form": form,
        "action_title": ACTIONS[action][0], "action": action,
        "action_links": [{"label": info[0], "url": support_url(key), "active": key == action} for key, info in permitted],
        "preview": preview, "confirmation": confirmation, "history": recent,
    })


def dashboard(site, request):
    if not request.user.has_perm("billing.view_finance_dashboard"):
        raise PermissionDenied
    now = timezone.now()
    try:
        days = max(1, min(365, int(request.GET.get("days", "30"))))
    except ValueError:
        days = 30
    since = now - timedelta(days=days)
    # Receipts are grouped by paid_at, including late payments on older orders.
    paid = Order.objects.filter(paid_at__gte=since, paid_at__lte=now, status__in=["PAID", "FULFILLED"])
    new_orders = Order.objects.filter(created_at__gte=since, created_at__lte=now)
    ledger = WalletLedger.objects.filter(created_at__gte=since, created_at__lte=now)
    receipts = paid.aggregate(count=Count("id"), amount=Sum("amount"))
    wallets = Wallet.objects.aggregate(total=Sum("balance"), reserved=Sum("reserved"))
    review = PaymentCheckout.objects.filter(needs_review=True).select_related("attempt__order__user").order_by("updated_at")
    delivery = Order.objects.filter(status="PAID").select_related("user").order_by("paid_at")
    user_query = request.GET.get("username", "").strip()[:150]
    found = get_user_model().objects.filter(username=user_query).first() if user_query else None
    review_rows, delivery_rows = list(review[:15]), list(delivery[:15])
    for row in review_rows:
        row.support_url = support_url("review_payment", row.pk)
    for row in delivery_rows:
        row.support_url = support_url("retry_delivery", row.pk)
    return TemplateResponse(request, "admin/billing/dashboard.html", {
        **site.each_context(request), "title": "داشبورد مالی", "days": days, "as_of": now,
        "cards": [
            {"label": "سفارش جدید در بازه", "value": new_orders.count()},
            {"label": "پرداخت تأییدشده در بازه", "value": receipts["count"]},
            {"label": "مبلغ پرداخت‌های تأییدشده (ریال)", "value": receipts["amount"] or 0},
            {"label": "تحویل در بازه", "value": Order.objects.filter(fulfilled_at__gte=since, fulfilled_at__lte=now).count()},
            {"label": "مصرف درخواست در بازه", "value": ledger.filter(kind="CONSUME").count()},
            {"label": "VIP فعال اکنون", "value": VIPSubscription.objects.filter(revoked_at__isnull=True, starts_at__lte=now, ends_at__gt=now).count()},
        ],
        "wallets": wallets, "review_count": review.count(), "delivery_count": delivery.count(),
        "review_rows": review_rows, "delivery_rows": delivery_rows,
        "products": paid.order_by().values("product_snapshot__title").annotate(count=Count("id"), amount=Sum("amount")).order_by("-amount"),
        "recent": new_orders.select_related("user").order_by("-created_at")[:20],
        "username": user_query, "found_user": found,
        "found_wallet": Wallet.objects.filter(user=found).first() if found else None,
        "grant_url": support_url("grant", found.username) if found else "",
    })
