"""Unit tests for Razorpay payment client, subscription manager, signature verification, and webhook handling."""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.billing import Plan, Subscription, SubscriptionStatus
from app.models.tenant import Tenant
from app.services.billing.razorpay_client import (
    RazorpayClient,
    RazorpayPaymentResult,
    RazorpaySubscriptionResult,
)
from app.services.billing.subscription_manager import (
    BillingNotConfiguredError,
    PlanChangeNotSupportedError,
    SubscriptionManager,
)


class FakeRazorpayClient(RazorpayClient):
    """Fake Razorpay client for testing signature verification and API calls.

    `fetch_payment` is stubbed because `verify_and_activate` now confirms the
    payment with Razorpay before activating — a valid signature alone is no
    longer sufficient. Override `payment_result` to simulate failed, pending,
    underpaid, or mis-attributed payments.
    """

    def __init__(
        self,
        key_id="rzp_test_123",
        key_secret="secret_123",  # noqa: S107 - test fixture, not a real credential
        payment_result: RazorpayPaymentResult | None = None,
    ):
        super().__init__(key_id=key_id, key_secret=key_secret)
        self.payment_result = payment_result
        self.fetch_payment_calls: list[str] = []

    async def fetch_payment(self, payment_id: str) -> RazorpayPaymentResult:
        self.fetch_payment_calls.append(payment_id)
        if self.payment_result is not None:
            return self.payment_result
        return RazorpayPaymentResult(
            payment_id=payment_id,
            status="captured",
            amount=499500,
            currency="INR",
            subscription_id=None,
        )


@pytest.mark.asyncio
async def test_razorpay_payment_signature_verification():
    client = FakeRazorpayClient(key_id="rzp_test_123", key_secret="secret_123")  # noqa: S106
    sub_id = "sub_test123"
    pay_id = "pay_test456"

    # Compute valid signature
    valid_sig = hmac.new(
        b"secret_123",
        f"{pay_id}|{sub_id}".encode(),
        "sha256",
    ).hexdigest()

    assert client.verify_payment_signature(sub_id, pay_id, valid_sig) is True
    assert client.verify_payment_signature(sub_id, pay_id, "invalid_sig") is False


@pytest.mark.asyncio
async def test_subscription_manager_verify_and_activate_unit():
    client = FakeRazorpayClient(key_id="rzp_test_123", key_secret="secret_123")  # noqa: S106
    mgr = SubscriptionManager(client)

    tenant_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    mock_sub = Subscription(
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        status=SubscriptionStatus.incomplete,
        razorpay_customer_id="cust_123",
        razorpay_subscription_id="sub_rzp_test_99",
        current_period_start=now,
        current_period_end=now + timedelta(days=1),
    )

    mock_session = AsyncMock()
    mock_session.scalar.return_value = mock_sub
    # verify_and_activate now loads the plan to check the amount charged.
    mock_session.get.return_value = _plan(price=499500, rzp_id="plan_x")

    sub_id = "sub_rzp_test_99"
    pay_id = "pay_rzp_test_88"
    valid_sig = hmac.new(
        b"secret_123",
        f"{pay_id}|{sub_id}".encode(),
        "sha256",
    ).hexdigest()

    # Verify and activate
    updated = await mgr.verify_and_activate(
        mock_session,
        tenant_id=tenant_id,
        subscription_id=sub_id,
        payment_id=pay_id,
        signature=valid_sig,
    )

    assert updated.status == SubscriptionStatus.active

    # Invalid signature failure
    with pytest.raises(ValueError, match="Invalid Razorpay payment signature"):
        await mgr.verify_and_activate(
            mock_session,
            tenant_id=tenant_id,
            subscription_id=sub_id,
            payment_id=pay_id,
            signature="bad_sig",
        )


@pytest.mark.asyncio
async def test_handle_razorpay_webhook_events_unit():
    client = FakeRazorpayClient()
    mgr = SubscriptionManager(client)

    tenant_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    mock_sub = Subscription(
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        status=SubscriptionStatus.incomplete,
        razorpay_customer_id="cust_abc",
        razorpay_subscription_id="sub_wh_test_1",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )

    mock_session = AsyncMock()
    mock_session.scalar.return_value = mock_sub

    # 1. Test subscription.authenticated event
    event_sub_auth = {
        "event": "subscription.authenticated",
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_wh_test_1",
                    "status": "authenticated",
                }
            }
        },
    }
    await mgr.handle_razorpay_event(mock_session, event_sub_auth)
    # The subscription *entity* is now the source of truth, and Razorpay's
    # "authenticated" means the mandate is set up — not that a payment has been
    # captured. It maps to `trialing`, which still grants workspace access.
    # This previously asserted `active` because the event-type branch
    # unconditionally overwrote whatever the entity said.
    assert mock_sub.status == SubscriptionStatus.trialing

    # 2. Test payment.failed event
    event_pay_failed = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_fail_123",
                    "subscription_id": "sub_wh_test_1",
                    "status": "failed",
                }
            }
        },
    }
    await mgr.handle_razorpay_event(mock_session, event_pay_failed)
    assert mock_sub.status == SubscriptionStatus.past_due

    # 3. Test payment.captured event
    event_pay_captured = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_cap_123",
                    "subscription_id": "sub_wh_test_1",
                    "status": "captured",
                }
            }
        },
    }
    await mgr.handle_razorpay_event(mock_session, event_pay_captured)
    assert mock_sub.status == SubscriptionStatus.active


# ──────────────────────────────────────────────────────────────────────────────
# Regression tests for the three P0 defects in start_subscription.
#
# The original bug chain: every seeded plan has a NULL `razorpay_plan_id`
# (005 never populated it, and sync_razorpay_plans.py can't run without
# credentials), so a *priced* plan fell into the enterprise/custom-billing
# branch and was marked `active` with no payment taken. SubscriptionGate then
# opened the workspace. Nothing here existed to catch it — there was no test
# for start_subscription at all.
# ──────────────────────────────────────────────────────────────────────────────


def _mock_session(*, plan, tenant, live_sub=None, prior_sub_id=None):
    """AsyncMock session wired for start_subscription's access pattern.

    Calls, in order: get(Plan) → get(Tenant) → execute() for the live-slot
    lookup → scalar() for trial eligibility.
    """
    session = AsyncMock()
    session.get.side_effect = [plan, tenant]
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=live_sub))
    session.scalar.return_value = prior_sub_id
    return session


def _plan(plan_id="growth_monthly", *, price=499500, rzp_id=None, trial_days=14):
    return Plan(
        id=plan_id,
        display_name="Growth",
        tier="growth",
        base_price_cents=price,
        billing_interval="month",
        razorpay_plan_id=rzp_id,
        trial_days=trial_days,
        included_quotas={},
        overage_rates_cents={},
        is_active=True,
    )


def _tenant(tenant_id):
    return Tenant(id=tenant_id, slug="acme", display_name="Acme Corp")


@pytest.mark.asyncio
async def test_priced_plan_without_razorpay_id_is_refused():
    """P0-1: a plan that costs money must have a payment provider behind it.

    Before the fix this returned an `active` subscription and unlocked the
    workspace for free.
    """
    tenant_id = uuid.uuid4()
    plan = _plan(price=1499500, rzp_id=None, trial_days=0)
    session = _mock_session(plan=plan, tenant=_tenant(tenant_id), prior_sub_id="prior")

    mgr = SubscriptionManager(FakeRazorpayClient())

    with pytest.raises(BillingNotConfiguredError, match="razorpay_plan_id"):
        await mgr.start_subscription(
            session,
            tenant_id=tenant_id,
            plan_id="scale_monthly",
            billing_email="someone@example.com",
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_zero_cost_plan_without_razorpay_id_is_incomplete_not_active():
    """P0-1: custom-billed plans are entitled out of band, not by this endpoint."""
    tenant_id = uuid.uuid4()
    plan = _plan("enterprise_monthly", price=0, rzp_id=None, trial_days=0)
    session = _mock_session(plan=plan, tenant=_tenant(tenant_id), prior_sub_id="prior")

    mgr = SubscriptionManager(FakeRazorpayClient())
    sub = await mgr.start_subscription(
        session,
        tenant_id=tenant_id,
        plan_id="enterprise_monthly",
        billing_email="ops@example.com",
    )

    assert sub.status is SubscriptionStatus.incomplete
    assert sub.status is not SubscriptionStatus.active


@pytest.mark.asyncio
async def test_trial_length_comes_from_plan_not_caller():
    """P0-2: `trial_days` is no longer accepted as a parameter at all."""
    import inspect

    params = inspect.signature(SubscriptionManager.start_subscription).parameters
    assert "trial_days" not in params, "trial_days must not be caller-supplied"

    tenant_id = uuid.uuid4()
    plan = _plan(price=0, rzp_id=None, trial_days=14)
    session = _mock_session(plan=plan, tenant=_tenant(tenant_id), prior_sub_id=None)

    mgr = SubscriptionManager(FakeRazorpayClient())
    sub = await mgr.start_subscription(
        session,
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        billing_email="new@example.com",
    )

    assert sub.status is SubscriptionStatus.trialing
    span_days = (sub.current_period_end - sub.current_period_start).days
    assert span_days == 14


@pytest.mark.asyncio
async def test_second_trial_is_not_granted():
    """P0-2: one trial per tenant, enforced server-side.

    `prior_sub_id` non-None means the tenant has held a subscription before,
    so the trial is burned even though the plan still advertises 14 days.
    """
    tenant_id = uuid.uuid4()
    plan = _plan(price=0, rzp_id=None, trial_days=14)
    session = _mock_session(
        plan=plan, tenant=_tenant(tenant_id), live_sub=None, prior_sub_id=uuid.uuid4()
    )

    mgr = SubscriptionManager(FakeRazorpayClient())
    sub = await mgr.start_subscription(
        session,
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        billing_email="repeat@example.com",
    )

    assert sub.status is SubscriptionStatus.incomplete, "second trial must not be granted"


@pytest.mark.asyncio
async def test_duplicate_subscription_returns_existing():
    """P0-3: a double-submit must not create a second Razorpay subscription."""
    tenant_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    existing = Subscription(
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        status=SubscriptionStatus.active,
        razorpay_subscription_id="sub_existing_1",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    plan = _plan(rzp_id="plan_rzp_1")
    session = _mock_session(plan=plan, tenant=_tenant(tenant_id), live_sub=existing)

    mgr = SubscriptionManager(FakeRazorpayClient())
    sub = await mgr.start_subscription(
        session,
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        billing_email="dup@example.com",
    )

    assert sub is existing
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_switching_plans_while_live_is_rejected():
    """P0-3: 'Switch to this plan' must not stack a second subscription.

    Plan changes need proration and cancellation of the old mandate; until
    that exists, refuse rather than double-bill.
    """
    tenant_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    existing = Subscription(
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        status=SubscriptionStatus.active,
        razorpay_subscription_id="sub_existing_2",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    plan = _plan("scale_monthly", price=1499500, rzp_id="plan_rzp_2")
    session = _mock_session(plan=plan, tenant=_tenant(tenant_id), live_sub=existing)

    mgr = SubscriptionManager(FakeRazorpayClient())

    with pytest.raises(PlanChangeNotSupportedError):
        await mgr.start_subscription(
            session,
            tenant_id=tenant_id,
            plan_id="scale_monthly",
            billing_email="switch@example.com",
        )

    session.add.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# Regression tests for the P1 defects.
#
# These cover the second wave of findings: activation on a signature alone,
# webhook event ordering, the `except Exception` around signature verification,
# and the yearly `total_count` miscalculation.
# ──────────────────────────────────────────────────────────────────────────────


def _sub(tenant_id, *, rzp_sub_id="sub_p1", status=SubscriptionStatus.incomplete, days=1):
    now = datetime.now(tz=UTC)
    return Subscription(
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        status=status,
        razorpay_customer_id="cust_p1",
        razorpay_subscription_id=rzp_sub_id,
        current_period_start=now,
        current_period_end=now + timedelta(days=days),
        subscription_metadata={},
    )


def _sig(secret: bytes, sub_id: str, pay_id: str) -> str:
    return hmac.new(secret, f"{pay_id}|{sub_id}".encode(), "sha256").hexdigest()


@pytest.mark.asyncio
async def test_verify_does_not_activate_when_payment_not_captured():
    """P1: a valid signature does not mean the money moved.

    Razorpay signs the (payment_id, subscription_id) pair regardless of whether
    the payment was captured. Activating on the signature alone unlocked the
    workspace for failed and merely-authorized payments.
    """
    tenant_id = uuid.uuid4()
    sub_id, pay_id = "sub_p1", "pay_p1"
    client = FakeRazorpayClient(
        payment_result=RazorpayPaymentResult(
            payment_id=pay_id,
            status="failed",
            amount=499500,
            currency="INR",
            subscription_id=sub_id,
        )
    )
    mgr = SubscriptionManager(client)
    row = _sub(tenant_id, rzp_sub_id=sub_id)

    session = AsyncMock()
    session.scalar.return_value = row
    session.get.return_value = _plan(price=499500, rzp_id="plan_x")

    with pytest.raises(ValueError, match="not been captured"):
        await mgr.verify_and_activate(
            session,
            tenant_id=tenant_id,
            subscription_id=sub_id,
            payment_id=pay_id,
            signature=_sig(b"secret_123", sub_id, pay_id),
        )
    assert row.status is SubscriptionStatus.incomplete


@pytest.mark.asyncio
async def test_verify_rejects_underpayment():
    """P1: the amount charged must cover the plan price."""
    tenant_id = uuid.uuid4()
    sub_id, pay_id = "sub_p1", "pay_p1"
    client = FakeRazorpayClient(
        payment_result=RazorpayPaymentResult(
            payment_id=pay_id,
            status="captured",
            amount=100,  # ₹1 against a ₹4,995 plan
            currency="INR",
            subscription_id=sub_id,
        )
    )
    mgr = SubscriptionManager(client)
    row = _sub(tenant_id, rzp_sub_id=sub_id)

    session = AsyncMock()
    session.scalar.return_value = row
    session.get.return_value = _plan(price=499500, rzp_id="plan_x")

    with pytest.raises(ValueError, match="amount does not match"):
        await mgr.verify_and_activate(
            session,
            tenant_id=tenant_id,
            subscription_id=sub_id,
            payment_id=pay_id,
            signature=_sig(b"secret_123", sub_id, pay_id),
        )
    assert row.status is SubscriptionStatus.incomplete


@pytest.mark.asyncio
async def test_verify_rejects_payment_for_a_different_subscription():
    """P1: the payment entity is authoritative about what it settled."""
    tenant_id = uuid.uuid4()
    sub_id, pay_id = "sub_p1", "pay_p1"
    client = FakeRazorpayClient(
        payment_result=RazorpayPaymentResult(
            payment_id=pay_id,
            status="captured",
            amount=499500,
            currency="INR",
            subscription_id="sub_someone_else",
        )
    )
    mgr = SubscriptionManager(client)
    row = _sub(tenant_id, rzp_sub_id=sub_id)

    session = AsyncMock()
    session.scalar.return_value = row
    session.get.return_value = _plan(price=499500, rzp_id="plan_x")

    with pytest.raises(ValueError, match="does not belong"):
        await mgr.verify_and_activate(
            session,
            tenant_id=tenant_id,
            subscription_id=sub_id,
            payment_id=pay_id,
            signature=_sig(b"secret_123", sub_id, pay_id),
        )
    assert row.status is SubscriptionStatus.incomplete


@pytest.mark.asyncio
async def test_verify_extends_annual_period_by_a_year_not_a_month():
    """P2: annual subscribers had period_end set 30 days out, re-locking early."""
    tenant_id = uuid.uuid4()
    sub_id, pay_id = "sub_yr", "pay_yr"
    mgr = SubscriptionManager(FakeRazorpayClient())
    row = _sub(tenant_id, rzp_sub_id=sub_id)
    row.plan_id = "growth_yearly"

    session = AsyncMock()
    session.scalar.return_value = row
    session.get.return_value = _plan("growth_yearly", price=499500, rzp_id="plan_y")
    session.get.return_value.billing_interval = "year"

    before = datetime.now(tz=UTC)
    await mgr.verify_and_activate(
        session,
        tenant_id=tenant_id,
        subscription_id=sub_id,
        payment_id=pay_id,
        signature=_sig(b"secret_123", sub_id, pay_id),
    )
    assert row.status is SubscriptionStatus.active
    assert (row.current_period_end - before).days > 300


@pytest.mark.asyncio
async def test_halted_subscription_charged_event_does_not_activate():
    """P1: entity status wins over event type.

    A `halted` subscription emitting `subscription.charged` was recorded as
    `active` — a delinquent account holding an unlocked workspace.
    """
    tenant_id = uuid.uuid4()
    mgr = SubscriptionManager(FakeRazorpayClient())
    row = _sub(tenant_id, rzp_sub_id="sub_h", status=SubscriptionStatus.active)

    session = AsyncMock()
    session.scalar.return_value = row
    session.get.return_value = _plan(price=499500, rzp_id="plan_x")

    await mgr.handle_razorpay_event(
        session,
        {
            "event": "subscription.charged",
            "created_at": 1_700_000_000,
            "payload": {"subscription": {"entity": {"id": "sub_h", "status": "halted"}}},
        },
    )
    assert row.status is SubscriptionStatus.past_due


@pytest.mark.asyncio
async def test_out_of_order_activation_does_not_resurrect_cancelled_subscription():
    """P1: Razorpay retries out of order.

    A delayed `subscription.activated` arriving after a cancellation used to
    un-cancel the subscription, restoring access the customer had ended.
    """
    tenant_id = uuid.uuid4()
    mgr = SubscriptionManager(FakeRazorpayClient())
    row = _sub(tenant_id, rzp_sub_id="sub_o")

    session = AsyncMock()
    session.scalar.return_value = row
    session.get.return_value = _plan(price=499500, rzp_id="plan_x")

    await mgr.handle_razorpay_event(
        session,
        {
            "event": "subscription.cancelled",
            "created_at": 1_700_000_200,
            "payload": {"subscription": {"entity": {"id": "sub_o", "status": "cancelled"}}},
        },
    )
    assert row.status is SubscriptionStatus.cancelled

    # Older event, delivered late.
    await mgr.handle_razorpay_event(
        session,
        {
            "event": "subscription.activated",
            "created_at": 1_700_000_100,
            "payload": {"subscription": {"entity": {"id": "sub_o", "status": "active"}}},
        },
    )
    assert row.status is SubscriptionStatus.cancelled


@pytest.mark.asyncio
async def test_signature_verification_raises_when_secret_missing():
    """P1: a config error must not be reported as a forged signature.

    `except Exception` around the SDK call swallowed the "Razorpay is not
    configured" RuntimeError and fell through to a manual HMAC, so an operator
    misconfiguration looked identical to an attack.
    """
    client = RazorpayClient(key_id=None, key_secret=None)
    with pytest.raises(RuntimeError, match="RAZORPAY_KEY_SECRET"):
        client.verify_payment_signature("sub_x", "pay_x", "sig_x")


def test_yearly_plans_do_not_request_120_years_of_billing():
    """P2: total_count is a count of cycles, not months."""
    client = RazorpayClient(key_id="k", key_secret="s", total_count=120)  # noqa: S106
    assert client.cycles_for("month") == 120
    assert client.cycles_for("year") == 10


@pytest.mark.asyncio
async def test_create_subscription_uses_only_provider_supported_fields():
    """Razorpay creates and links the customer during authorisation.

    ``customer_id`` and ``callback_url`` are Checkout fields, not accepted by
    the create-subscription API. Sending either makes Razorpay reject the
    request before Checkout can open.
    """
    sdk = MagicMock()
    sdk.subscription.create.return_value = {
        "id": "sub_test_123",
        "status": "created",
        "current_start": None,
        "current_end": None,
        "short_url": "https://rzp.io/i/test",
    }
    client = RazorpayClient(key_id="k", key_secret="s", total_count=120)  # noqa: S106
    client._client = sdk

    await client.create_subscription(
        plan_id="plan_test_123",
        billing_interval="month",
    )

    sdk.subscription.create.assert_called_once_with(
        data={
            "plan_id": "plan_test_123",
            "total_count": 120,
            "customer_notify": 1,
        }
    )


@pytest.mark.asyncio
async def test_create_subscription_wraps_provider_rejection():
    """A Razorpay API rejection must not escape as an unhandled HTTP 500."""
    from razorpay.errors import BadRequestError

    sdk = MagicMock()
    sdk.subscription.create.side_effect = BadRequestError("provider rejected request")
    client = RazorpayClient(key_id="k", key_secret="s")  # noqa: S106
    client._client = sdk

    with pytest.raises(RuntimeError, match="Razorpay rejected subscription setup"):
        await client.create_subscription(plan_id="plan_test_123")


@pytest.mark.asyncio
async def test_manager_does_not_create_customer_before_subscription_authorisation():
    """Checkout, not the server, creates and links Razorpay's customer."""
    tenant_id = uuid.uuid4()
    plan = _plan(price=499500, rzp_id="plan_test_123", trial_days=14)
    session = _mock_session(
        plan=plan,
        tenant=_tenant(tenant_id),
        prior_sub_id=uuid.uuid4(),
    )
    session.add = MagicMock()
    provider = MagicMock(spec=RazorpayClient)
    provider.upsert_customer = AsyncMock()
    provider.create_subscription = AsyncMock(
        return_value=RazorpaySubscriptionResult(
            subscription_id="sub_test_123",
            status="created",
            current_period_start=None,
            current_period_end=None,
            short_url="https://rzp.io/i/test",
        )
    )

    await SubscriptionManager(provider).start_subscription(
        session,
        tenant_id=tenant_id,
        plan_id="growth_monthly",
        billing_email="buyer@example.com",
    )

    provider.upsert_customer.assert_not_awaited()
    provider.create_subscription.assert_awaited_once_with(
        plan_id="plan_test_123",
        trial_days=0,
        billing_interval="month",
    )


@pytest.mark.asyncio
async def test_notifications_are_buffered_until_flush():
    """P2: realtime events must not escape before the transaction commits."""
    tenant_id = uuid.uuid4()
    mgr = SubscriptionManager(FakeRazorpayClient())
    plan = _plan(price=0, rzp_id=None, trial_days=0)
    session = _mock_session(plan=plan, tenant=_tenant(tenant_id))

    await mgr.start_subscription(
        session, tenant_id=tenant_id, plan_id="growth_monthly", billing_email="a@b.com"
    )
    # Buffered, not published.
    assert len(mgr._pending_events) == 1

    mgr.discard_notifications()
    assert mgr._pending_events == []


@pytest.mark.asyncio
async def test_razorpay_order_signature_verification():
    """Standard Web Checkout: verify HMAC-SHA256(order_id|payment_id, secret)."""
    client = RazorpayClient(key_id="rzp_test_123", key_secret="secret_123")  # noqa: S106
    order_id = "order_test999"
    pay_id = "pay_test888"

    valid_sig = hmac.new(
        b"secret_123",
        f"{order_id}|{pay_id}".encode(),
        "sha256",
    ).hexdigest()

    assert client.verify_order_signature(order_id, pay_id, valid_sig) is True
    assert client.verify_order_signature(order_id, pay_id, "forged_signature") is False


@pytest.mark.asyncio
async def test_razorpay_create_order_min_amount_validation():
    """Razorpay orders require amount >= 100 paise (₹1.00)."""
    client = RazorpayClient(key_id="rzp_test_123", key_secret="secret_123")  # noqa: S106

    with pytest.raises(ValueError, match="at least 100 paise"):
        await client.create_order(amount=99)
