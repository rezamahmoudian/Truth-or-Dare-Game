"""Gateway adapter contract. No bank or simulated gateway is enabled by default."""
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.module_loading import import_string

from apps.core.errors import DomainError


@dataclass(frozen=True)
class PaymentRequest:
    # The adapter must preserve this key across every create/recover call.
    key: str
    amount: int
    currency: str
    callback_url: str
    description: str


@dataclass(frozen=True)
class CheckoutResult:
    reference: str
    redirect_url: str


@dataclass(frozen=True)
class VerificationResult:
    status: str  # VERIFIED, PENDING, FAILED (definitive, from server verification)
    reference: str
    transaction_id: str = ""
    amount: int | None = None
    currency: str = ""


class GatewayUnavailable(Exception):
    """Unknown result / timeout. Never equivalent to a declined payment."""


class GatewayDeclined(Exception):
    """Definitive refusal to CREATE a checkout, with no payable transaction."""


class Gateway:
    # Set true only if start() safely recovers the SAME checkout after a timeout.
    start_is_idempotent = False
    is_test = False
    redirect_hosts: tuple[str, ...] = ()

    def configured(self) -> bool:
        return False

    def start(self, payment: PaymentRequest) -> CheckoutResult:
        raise NotImplementedError

    def verify(self, *, reference: str, amount: int, currency: str) -> VerificationResult:
        # Must query the provider using server credentials and bounded timeouts.
        # The result must include its verified amount/currency, not echoed input.
        raise NotImplementedError


def public_origin():
    value = settings.BILLING_PUBLIC_BASE_URL.rstrip("/")
    try:
        parts = urlsplit(value)
        parts.port  # Validate malformed/overflowing ports before generating URLs.
    except ValueError:
        raise DomainError("payment_unavailable", "نشانی بازگشت پرداخت معتبر نیست.", 503) from None
    local = settings.DEBUG and parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")
    if not value or any(c.isspace() for c in value) or (parts.scheme != "https" and not local) or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path:
        raise DomainError("payment_unavailable", "تنظیمات پرداخت هنوز آماده نیست.", 503)
    return value


def get_gateway(name=None):
    name = settings.BILLING_GATEWAY if name is None else name
    try:
        path = settings.BILLING_GATEWAY_ADAPTERS.get(name)
        gateway = import_string(path)() if path else None
        if not isinstance(gateway, Gateway) or (gateway.is_test and not settings.DEBUG) or not gateway.configured():
            raise ValueError("unconfigured")
    except Exception:
        raise DomainError("payment_unavailable", "درگاه پرداخت هنوز فعال نیست.", 503) from None
    return gateway


def payments_enabled():
    if not settings.BILLING_ORDERS_ENABLED or not settings.BILLING_PAYMENTS_ENABLED:
        return False
    try:
        public_origin()
        get_gateway()
        return True
    except DomainError:
        return False


def valid_redirect(gateway, url):
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname in gateway.redirect_hosts
                and parts.port in (None, 443) and not parts.username and not parts.password
                and not parts.fragment and not any(c.isspace() or ord(c) < 32 for c in url)
                and len(url) <= 2000)
    except (ValueError, TypeError):
        return False
