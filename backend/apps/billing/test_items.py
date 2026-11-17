from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import connections, IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.chat.models import Conversation, Participant, Message
from apps.chat import services as chat
from apps.core.errors import DomainError
from apps.game.models import GameSession, Prompt
from apps.game import services as game
from apps.users.models import Block
from .tests import Fixtures
from .models import DigitalItem, InventoryGrant, ItemUse, Product, ProductOffer, UserAppearance, RewardSession
from . import items, rewards, services, vip


class ItemFixtures(Fixtures):
    def setUp(self):
        super().setUp()
        for user in (self.user, self.other):
            user.display_name = user.username
            user.birth_date = date(1995, 1, 1)
            user.gender = "F"
            user.save()
        self.room = Conversation.objects.create(type="DIRECT", max_players=2, owner=self.user)
        Participant.objects.bulk_create([Participant(conversation=self.room, user=u) for u in (self.user, self.other)])

    def good(self, kind="GIFT", visual="rose", units=1):
        product = Product.objects.create(key=str(uuid4()), title="آیتم", kind="ITEM", credits=0, is_active=True)
        item = DigitalItem.objects.create(product=product, kind=kind, visual=visual, units=units)
        offer = ProductOffer.objects.create(key=str(uuid4()), product=product, amount=50000, is_active=True)
        return item, offer

    def buy(self, kind="GIFT", visual="rose", units=1):
        item, offer = self.good(kind, visual, units)
        if kind == "PACK":
            Prompt.objects.create(pack=item, text=str(uuid4()), type="TRUTH", is_active=True, review_status="APPROVED")
        order = self.purchased(offer=offer)
        return InventoryGrant.objects.get(order=order)

    def send(self, grant, key="send", **kwargs):
        return items.use_item(self.user, grant.pk, key, self.room.pk, self.other.pk, **kwargs)


@override_settings(BILLING_ORDERS_ENABLED=True)
@override_settings(MONETIZATION_ENABLED=True)
class ItemTests(ItemFixtures, TestCase):
    def test_last_gift_retry_after_inventory_refresh_returns_original_message(self):
        grant = self.buy()
        api = APIClient()
        api.force_authenticate(self.user)
        payload = {"grant_id": grant.pk, "idempotency_key": "lost-response",
                   "conversation_id": str(self.room.pk), "recipient_id": self.other.pk}
        sent = api.post("/api/billing/inventory/use/", payload, format="json")
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(api.get("/api/billing/inventory/").data["items"][0]["remaining"], 0)
        recovered = api.post("/api/billing/inventory/use/", payload, format="json")
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(recovered.data["message"]["id"], sent.data["message"]["id"])
        self.assertEqual(ItemUse.objects.count(), 1)

    def test_gift_retry_survives_sender_leaving_chat(self):
        grant = self.buy()
        use = self.send(grant, key="leave-retry")
        chat.leave(self.user, self.room)
        replay = items.use_item(
            self.user,
            grant.pk,
            "leave-retry",
            self.room.pk,
            self.other.pk,
        )
        self.assertEqual(replay.pk, use.pk)
        grant.refresh_from_db()
        self.assertEqual(grant.remaining, 0)

    def test_spotlight_recovery_after_expiry_never_consumes_a_second_unit(self):
        grant = self.buy("SPOTLIGHT", "spotlight", 2)
        use = items.use_item(self.user, grant.pk, "lost-response")
        with patch("django.utils.timezone.now", return_value=use.ends_at + timedelta(seconds=1)):
            self.assertEqual(items.use_item(self.user, grant.pk, "lost-response").pk, use.pk)
        grant.refresh_from_db()
        self.assertEqual(grant.remaining, 1)

    def test_owned_reaction_cannot_bypass_block_or_closed_chat(self):
        message, _ = chat.post_message(conversation=self.room, sender=self.other, body="سلام")
        self.buy("REACTION", "💎")
        chat.set_reaction(self.user, message.pk, "💎", "add")
        Block.objects.create(blocker=self.other, blocked=self.user)
        for emoji in ("❤️", "💎"):
            with self.assertRaises(DomainError):
                chat.set_reaction(self.user, message.pk, emoji, "add")
        chat.set_reaction(self.user, message.pk, "💎", "remove")
        Block.objects.all().delete()
        self.room.status = "CLOSED"
        self.room.save()
        with self.assertRaises(DomainError):
            chat.set_reaction(self.user, message.pk, "💎", "add")
        self.assertFalse(message.reactions.exists())

    def test_deleted_message_cannot_receive_paid_reaction(self):
        message, _ = chat.post_message(conversation=self.room, sender=self.other, body="سلام")
        self.buy("REACTION", "💎")
        message.is_deleted = True
        message.save()
        with self.assertRaises(DomainError):
            chat.set_reaction(self.user, message.pk, "💎", "add")
        self.assertFalse(message.reactions.exists())

    def test_paid_delivery_once_without_spending_request_credits(self):
        grant = self.buy()
        services.fulfill_order(grant.order_id)
        self.assertEqual(InventoryGrant.objects.count(), 1)
        self.assert_balances(0)
        self.assertEqual(grant.snapshot["kind"], "GIFT")

    def test_delivery_never_before_verification(self):
        _, offer = self.good()
        order = self.order(offer=offer)
        with self.assertRaises(DomainError):
            services.fulfill_order(order.pk)
        self.assertFalse(InventoryGrant.objects.exists())

    def test_order_snapshot_not_current_product_drives_delivery(self):
        item, offer = self.good(units=3)
        order = self.order(offer=offer)
        item.units = 10
        item.save()
        self.verified(order)
        services.fulfill_order(order.pk)
        self.assertEqual(InventoryGrant.objects.get(order=order).remaining, 3)

    def test_permanent_duplicate_purchase_blocked_and_idempotent_order_replayed(self):
        grant = self.buy("FRAME", "aurora")
        order = grant.order
        self.assertEqual(services.create_order(user=self.user, offer_id=order.offer_id, idempotency_key=order.idempotency_key).pk, order.pk)
        with self.assertRaises(DomainError) as error:
            self.order(offer=order.offer)
        self.assertEqual(error.exception.code, "already_owned")

    def test_equip_requires_ownership_and_correct_slot_then_survives_vip_expiry(self):
        grant = self.buy("FRAME", "aurora")
        with self.assertRaises(DomainError):
            items.equip(self.other, "FRAME", grant.pk)
        with self.assertRaises(DomainError):
            items.equip(self.user, "NAME", grant.pk)
        items.equip(self.user, "FRAME", grant.pk)
        state = vip.for_user(self.user)
        self.assertFalse(state["active"])
        self.assertEqual(state["cosmetics"]["FRAME"]["visual"], "aurora")
        self.assertNotIn("grant_id", state["cosmetics"]["FRAME"])
        items.equip(self.user, "FRAME", None)
        self.assertEqual(vip.for_user(self.user)["cosmetics"], {})

    def test_gift_replay_has_one_message_one_debit_and_rejects_changed_target(self):
        grant = self.buy()
        use = self.send(grant)
        self.assertEqual(self.send(grant).pk, use.pk)
        self.assertEqual(Message.objects.filter(type="ITEM").count(), 1)
        grant.refresh_from_db()
        self.assertEqual(grant.remaining, 0)
        self.assertEqual(items.gift_summary(self.other)[0]["count"], 1)
        with self.assertRaises(DomainError):
            items.use_item(self.user, grant.pk, "send", self.room.pk, self.admin.pk)
        with self.assertRaises(DomainError):
            self.send(grant, key="again")

    def test_gift_blocked_in_closed_room_or_blocked_relationship(self):
        grant = self.buy()
        Block.objects.create(blocker=self.other, blocked=self.user)
        with self.assertRaises(DomainError):
            self.send(grant)
        grant.refresh_from_db()
        self.assertEqual(grant.remaining, 1)
        self.assertFalse(ItemUse.objects.exists())
        Block.objects.all().delete()
        self.room.status = "CLOSED"
        self.room.save()
        with self.assertRaises(DomainError):
            self.send(grant)

    def test_gifts_never_go_to_self_ai_or_outsider(self):
        grant = self.buy()
        for uid in (self.user.pk, self.admin.pk):
            with self.assertRaises(DomainError):
                items.use_item(self.user, grant.pk, str(uuid4()), self.room.pk, uid)
        self.other.is_ai = True
        self.other.save()
        with self.assertRaises(DomainError):
            self.send(grant)

    def test_stickers_are_owned_reusable_and_idempotent(self):
        grant = self.buy("STICKER", "party")
        for key in ("one", "two", "two"):
            items.use_item(self.user, grant.pk, key, self.room.pk)
        self.assertEqual(Message.objects.filter(type="ITEM").count(), 2)
        grant.refresh_from_db()
        self.assertEqual(grant.remaining, 1)

    def test_special_reaction_requires_ownership_but_regular_remains_free(self):
        message, _ = chat.post_message(conversation=self.room, sender=self.other, body="سلام")
        chat.set_reaction(self.user, message.pk, "❤️", "add")
        with self.assertRaises(DomainError):
            chat.set_reaction(self.user, message.pk, "💎", "add")
        self.buy("REACTION", "💎")
        chat.set_reaction(self.user, message.pk, "💎", "add")
        message.refresh_from_db()
        self.assertEqual(message.reactions.count(), 2)

    def test_spotlight_once_and_no_overlap_then_expires(self):
        grant = self.buy("SPOTLIGHT", "spotlight", 2)
        use = items.use_item(self.user, grant.pk, "spot")
        self.assertAlmostEqual(use.ends_at - use.created_at, timedelta(minutes=15), delta=timedelta(seconds=1))
        self.assertEqual(items.use_item(self.user, grant.pk, "spot").pk, use.pk)
        with self.assertRaises(DomainError):
            items.use_item(self.user, grant.pk, "overlap")
        with patch("django.utils.timezone.now", return_value=use.ends_at + timedelta(seconds=1)):
            self.assertFalse(items.spotlight_active(self.user.pk))
            items.use_item(self.user, grant.pk, "next")
        grant.refresh_from_db()
        self.assertEqual(grant.remaining, 0)

    def test_purchased_spotlight_appears_only_while_online(self):
        from apps.matchmaking.services import recently_active
        grant = self.buy("SPOTLIGHT", "spotlight")
        items.use_item(self.user, grant.pk, "spot")
        with patch("apps.chat.presence.app_online_ids", return_value=[self.user.pk]):
            listed = recently_active(self.other)
            self.assertTrue(listed[0]._spotlight)
        with patch("apps.chat.presence.app_online_ids", return_value=[]):
            self.assertEqual(recently_active(self.other), [])

    def test_paid_prompts_cannot_leak_into_free_game_or_unowned_session(self):
        grant = self.buy("PACK", "cards")
        free = Prompt.objects.create(text="سؤال رایگان", type="TRUTH", review_status="APPROVED")
        session = GameSession.objects.create(conversation=self.room, turn_order=[self.user.pk, self.other.pk])
        self.assertEqual(game._pick_prompt(session, "TRUTH").pk, free.pk)
        session.status = "ENDED"
        session.save()
        with self.assertRaises(DomainError):
            game.start_game(self.other, self.room, prompt_pack_id=grant.item_id)
        paid = game.start_game(self.user, self.room, prompt_pack_id=grant.item_id)
        self.assertEqual(game._pick_prompt(paid, "TRUTH").pack_id, grant.item_id)
        with self.assertRaises(DomainError):
            game._pick_prompt(paid, "TRUTH")

    def test_pack_not_sold_without_approved_prompts_and_free_prompt_cannot_move(self):
        item, offer = self.good("PACK", "cards")
        with self.assertRaises(DomainError):
            self.order(offer=offer)
        prompt = Prompt.objects.create(text="رایگان می‌ماند", type="TRUTH")
        prompt.pack = item
        with self.assertRaises(ValidationError):
            prompt.full_clean()

    def test_leaderboard_respects_blocks(self):
        grant = self.buy()
        self.send(grant)
        self.assertEqual(items.leaders(self.user)[0]["user"]["id"], self.other.pk)
        Block.objects.create(blocker=self.other, blocked=self.user)
        self.assertEqual(items.leaders(self.user), [])

    def test_api_cannot_grant_items_and_auth_required(self):
        api = APIClient()
        self.assertEqual(api.get("/api/billing/inventory/").status_code, 401)
        api.force_authenticate(self.other)
        grant = self.buy()
        result = api.post("/api/billing/inventory/use/", {"grant_id": grant.pk, "idempotency_key": "forge"}, format="json")
        self.assertEqual(result.status_code, 403)
        self.assertEqual(api.get("/api/billing/inventory/").data["items"], [])

    def test_sql_cannot_rewrite_inventory_or_gift_audit(self):
        grant = self.buy()
        use = self.send(grant)
        for action in (
            lambda: InventoryGrant.objects.filter(pk=grant.pk).update(remaining=10),
            lambda: InventoryGrant.objects.filter(pk=grant.pk).update(snapshot={}),
            lambda: ItemUse.objects.filter(pk=use.pk).update(recipient=self.admin),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                action()

    def test_text_message_id_cannot_impersonate_gift(self):
        grant = self.buy()
        text, _ = chat.post_message(conversation=self.room, sender=self.user, body="معمولی", client_id=f"item:{self.user.pk}:send")
        sent = self.send(grant)
        self.assertNotEqual(sent.message_id, text.pk)
        self.assertEqual(sent.message.type, "ITEM")


@override_settings(BILLING_ORDERS_ENABLED=True)
class ItemConcurrencyTests(ItemFixtures, TransactionTestCase):
    def test_two_sends_compete_for_last_gift(self):
        grant = self.buy()
        barrier = Barrier(2)
        def send(index):
            try:
                barrier.wait(timeout=10)
                return self.send(grant, key=str(index)).pk
            except DomainError as exc:
                return exc.code
            finally:
                connections.close_all()
        with patch("apps.billing.vip.notify_change"), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, [1, 2]))
        self.assertEqual(results.count("item_empty"), 1)
        self.assertEqual(ItemUse.objects.count(), 1)
        self.assertEqual(Message.objects.filter(type="ITEM").count(), 1)


@override_settings(BILLING_ORDERS_ENABLED=True, REWARDED_ADS_ENABLED=True, REWARDED_AD_PROVIDER="test", REWARDED_AD_DAILY_LIMIT=1)
@override_settings(MONETIZATION_ENABLED=True)
class RewardTests(ItemFixtures, TestCase):
    def test_callback_must_pass_adapter_verification(self):
        class RejectingProvider:
            def verify_callback(self, request):
                raise DomainError("invalid_signature", "مدرک معتبر نیست.", 403)
        with patch.dict(rewards.PROVIDERS, {"test": RejectingProvider()}):
            response = APIClient().post("/api/billing/rewards/callback/test/", {"watched": True, "reward": 999}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(InventoryGrant.objects.exists())

    def test_reward_is_off_without_provider_and_client_cannot_claim(self):
        self.assertFalse(rewards.status()["available"])
        with self.assertRaises(DomainError):
            rewards.start(self.user)
        api = APIClient()
        api.force_authenticate(self.user)
        self.assertEqual(api.post("/api/billing/rewards/callback/test/", {"watched": True}).status_code, 503)
        self.assertFalse(InventoryGrant.objects.exists())

    def test_verified_reward_once_capped_and_expires(self):
        item, _ = self.good("SPOTLIGHT", "spotlight")
        item.spotlight_minutes = 5
        item.save()
        with override_settings(REWARDED_ITEM_KEY=item.product.key), patch.dict(rewards.PROVIDERS, {"test": object()}):
            session = rewards.start(self.user)
            self.assertEqual(rewards.start(self.user).pk, session.pk)
            proof = rewards.VerifiedReward(str(session.pk), "event-1")
            grant = rewards.grant_verified("test", proof)
            self.assertEqual(rewards.grant_verified("test", proof).pk, grant.pk)
            with self.assertRaises(DomainError):
                rewards.start(self.user)
            self.assertEqual(InventoryGrant.objects.count(), 1)
            other_session = rewards.start(self.other)
            with self.assertRaises(DomainError) as conflict:
                rewards.grant_verified("test", rewards.VerifiedReward(str(other_session.pk), "event-1"))
            self.assertEqual(conflict.exception.code, "reward_conflict")
            with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=1)):
                new = rewards.start(self.user)
            with patch("django.utils.timezone.now", return_value=new.expires_at):
                with self.assertRaises(DomainError):
                    rewards.grant_verified("test", rewards.VerifiedReward(str(new.pk), "event-2"))
