"""E2EE crypto setup, private chat, and secure internal mail."""

from __future__ import annotations

import json
import math

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, get_membership, membership_required, station_module_required
from .avatars import initials_for
from .messaging import (
    ordered_pair,
    public_keys_for_users,
    serialize_message_for_client,
    station_content_users,
    user_can_access_conversation,
    validate_encrypted_payload,
)
from .models import (
    PrivateConversation,
    PrivateMessage,
    SecureMail,
    SecureMailRecipient,
    UserCryptoIdentity,
    UserProfile,
)
from .services import audit


def _json_body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
        return data if isinstance(data, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _require_crypto(user):
    return UserCryptoIdentity.objects.filter(user=user).first()


@require_http_methods(["GET", "POST"])
def crypto_setup(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('crypto_setup')}")
    identity = _require_crypto(request.user)
    if request.method == "POST" and request.headers.get("Content-Type", "").startswith("application/json"):
        body = _json_body(request)
        if not body or not isinstance(body, dict):
            return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
        raw_iterations = body.get("kdf_iterations")
        if raw_iterations is None or raw_iterations == "":
            iterations = 210_000
        else:
            if isinstance(raw_iterations, float) and not math.isfinite(raw_iterations):
                return JsonResponse({"ok": False, "error": "KDF-Iterationen ungültig."}, status=400)
            try:
                iterations = int(raw_iterations)
            except (TypeError, ValueError, OverflowError):
                return JsonResponse({"ok": False, "error": "KDF-Iterationen ungültig."}, status=400)
        public_jwk = body.get("public_jwk")
        wrapped = body.get("wrapped_private_jwk")
        salt = body.get("kdf_salt")
        if not isinstance(public_jwk, dict) or public_jwk.get("kty") != "EC" or public_jwk.get("crv") != "P-256":
            return JsonResponse({"ok": False, "error": "Öffentlicher Schlüssel ungültig."}, status=400)
        if not isinstance(wrapped, str) or len(wrapped) < 32 or len(wrapped) > 8000:
            return JsonResponse({"ok": False, "error": "Privater Schlüsselumschlag ungültig."}, status=400)
        if not isinstance(salt, str) or len(salt) < 16 or len(salt) > 128:
            return JsonResponse({"ok": False, "error": "Salt ungültig."}, status=400)
        if iterations < 100_000 or iterations > 1_000_000:
            return JsonResponse({"ok": False, "error": "KDF-Iterationen ungültig."}, status=400)
        if identity and not body.get("replace"):
            return JsonResponse({"ok": False, "error": "Schlüssel existieren bereits."}, status=400)
        with transaction.atomic():
            identity, _ = UserCryptoIdentity.objects.update_or_create(
                user=request.user,
                defaults={
                    "public_jwk": {
                        "kty": "EC",
                        "crv": "P-256",
                        "x": public_jwk.get("x"),
                        "y": public_jwk.get("y"),
                    },
                    "wrapped_private_jwk": wrapped,
                    "kdf_salt": salt,
                    "kdf_iterations": iterations,
                },
            )
            UserProfile.for_user(request.user)
            membership = get_membership(request.user)
            audit(
                request.user,
                membership.station if membership else None,
                "crypto.keys_upserted",
                identity,
                {"fields": ["public_jwk"]},
            )
        return JsonResponse({"ok": True})
    from .messaging import key_fingerprint

    return render(request, "core/crypto_setup.html", {
        "identity": identity,
        "has_keys": identity is not None,
        "fingerprint": key_fingerprint(identity.public_jwk) if identity else None,
    })


@require_GET
def crypto_bundle(request):
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "Nicht angemeldet."}, status=401)
    identity = _require_crypto(request.user)
    if not identity:
        return JsonResponse({"ok": False, "configured": False})
    return JsonResponse({
        "ok": True,
        "configured": True,
        "user_id": request.user.id,
        "public_jwk": identity.public_jwk,
        "wrapped_private_jwk": identity.wrapped_private_jwk,
        "kdf_salt": identity.kdf_salt,
        "kdf_iterations": identity.kdf_iterations,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("chat_enabled")
@require_GET
def station_member_keys(request):
    users = station_content_users(request.membership.station)
    return JsonResponse({
        "ok": True,
        "members": public_keys_for_users(users),
    })


@membership_required(CONTENT_ROLES)
@station_module_required("chat_enabled")
@require_http_methods(["GET", "POST"])
def private_chat_home(request):
    station = request.membership.station
    identity = _require_crypto(request.user)
    conversations = (
        PrivateConversation.objects.filter(station=station)
        .filter(Q(user_low=request.user) | Q(user_high=request.user))
        .select_related("user_low", "user_high")
        .order_by("-updated_at")[:50]
    )
    peers = []
    for item in conversations:
        other = item.other_user(request.user)
        peers.append({
            "id": item.pk,
            "other_id": other.id,
            "other_name": other.first_name or other.username,
            "initials": initials_for(other),
            "updated_at": item.updated_at,
        })
    colleagues = []
    keyed = {
        row["user_id"]: row["has_keys"]
        for row in public_keys_for_users(station_content_users(station).exclude(pk=request.user.pk))
    }
    for user in station_content_users(station).exclude(pk=request.user.pk):
        colleagues.append({
            "id": user.id,
            "label": user.first_name or user.username,
            "has_keys": keyed.get(user.id, False),
        })
    if request.method == "POST":
        peer_id = request.POST.get("peer_id") or (_json_body(request) or {}).get("peer_id")
        try:
            peer_id = int(peer_id)
        except (TypeError, ValueError):
            messages.error(request, "Bitte einen Kollegen wählen.")
            return redirect("private_chat_home")
        peer = get_object_or_404(
            station_content_users(station),
            pk=peer_id,
        )
        try:
            low, high = ordered_pair(request.user.id, peer.id)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("private_chat_home")
        conversation, _ = PrivateConversation.objects.get_or_create(
            station=station,
            user_low_id=low,
            user_high_id=high,
        )
        return redirect("private_chat_thread", pk=conversation.pk)
    return render(request, "core/private_chat_home.html", {
        "peers": peers,
        "colleagues": colleagues,
        "has_keys": identity is not None,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("chat_enabled")
@require_http_methods(["GET", "POST"])
def private_chat_thread(request, pk):
    station = request.membership.station
    conversation = get_object_or_404(PrivateConversation, pk=pk, station=station)
    if not user_can_access_conversation(request.user, conversation):
        raise Http404
    identity = _require_crypto(request.user)
    other = conversation.other_user(request.user)
    if request.method == "POST" and request.headers.get("Content-Type", "").startswith("application/json"):
        if not identity:
            return JsonResponse({"ok": False, "error": "Bitte zuerst Schlüssel einrichten."}, status=400)
        body = _json_body(request)
        if not body:
            return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
        try:
            payload = validate_encrypted_payload(
                body,
                required_recipient_ids={request.user.id, other.id},
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": " ".join(exc.messages)}, status=400)
        message = PrivateMessage.objects.create(
            conversation=conversation,
            author=request.user,
            ciphertext=payload["ciphertext"],
            nonce=payload["nonce"],
            key_wraps=payload["key_wraps"],
            algo=payload["algo"],
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])
        audit(request.user, station, "private_chat.message_created", message, {
            "fields": ["ciphertext"],
        })
        return JsonResponse({"ok": True, "id": message.pk})

    rows = list(
        PrivateMessage.objects.filter(conversation=conversation, is_hidden=False)
        .select_related("author")[:80]
    )
    rows.reverse()
    feed = [serialize_message_for_client(item, request.user.id) for item in rows]
    for index, item in enumerate(rows):
        feed[index]["author_name"] = item.author.first_name or item.author.username
        feed[index]["is_own"] = item.author_id == request.user.id
    peer_keys = public_keys_for_users([request.user, other])
    return render(request, "core/private_chat_thread.html", {
        "conversation": conversation,
        "other": other,
        "other_initials": initials_for(other),
        "feed": feed,
        "feed_json": json.dumps(feed),
        "peer_keys_json": json.dumps(peer_keys),
        "has_keys": identity is not None,
        "viewer_id": request.user.id,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("chat_enabled")
@require_http_methods(["GET", "POST"])
def secure_mail_inbox(request):
    station = request.membership.station
    identity = _require_crypto(request.user)
    received = (
        SecureMail.objects.filter(station=station, recipients__user=request.user)
        .select_related("sender")
        .distinct()[:40]
    )
    sent = SecureMail.objects.filter(station=station, sender=request.user).select_related("sender")[:40]
    colleagues = public_keys_for_users(station_content_users(station).exclude(pk=request.user.pk))
    if request.method == "POST" and request.headers.get("Content-Type", "").startswith("application/json"):
        if not identity:
            return JsonResponse({"ok": False, "error": "Bitte zuerst Schlüssel einrichten."}, status=400)
        body = _json_body(request)
        if not body:
            return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
        recipient_ids = body.get("recipient_ids") or []
        if not isinstance(recipient_ids, list) or not recipient_ids:
            return JsonResponse({"ok": False, "error": "Bitte Empfänger wählen."}, status=400)
        try:
            recipient_ids = sorted({int(item) for item in recipient_ids})
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Empfänger ungültig."}, status=400)
        if request.user.id in recipient_ids:
            return JsonResponse({"ok": False, "error": "Eigenversand ist nicht vorgesehen."}, status=400)
        allowed = set(station_content_users(station).filter(pk__in=recipient_ids).values_list("id", flat=True))
        if set(recipient_ids) != allowed:
            return JsonResponse({"ok": False, "error": "Empfänger gehören nicht zur Wache."}, status=400)
        required = set(recipient_ids) | {request.user.id}
        try:
            payload = validate_encrypted_payload(body, required_recipient_ids=required)
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": " ".join(exc.messages)}, status=400)
        with transaction.atomic():
            mail = SecureMail.objects.create(
                station=station,
                sender=request.user,
                ciphertext=payload["ciphertext"],
                nonce=payload["nonce"],
                key_wraps=payload["key_wraps"],
                algo=payload["algo"],
            )
            SecureMailRecipient.objects.bulk_create([
                SecureMailRecipient(mail=mail, user_id=user_id) for user_id in recipient_ids
            ])
            audit(request.user, station, "secure_mail.created", mail, {
                "fields": ["ciphertext", "recipients"],
                "recipient_count": len(recipient_ids),
            })
        return JsonResponse({"ok": True, "id": mail.pk, "redirect": reverse("secure_mail_detail", args=[mail.pk])})

    return render(request, "core/secure_mail_inbox.html", {
        "received": received,
        "sent": sent,
        "colleagues_json": json.dumps(colleagues),
        "has_keys": identity is not None,
        "viewer_id": request.user.id,
    })


@membership_required(CONTENT_ROLES)
@station_module_required("chat_enabled")
@require_GET
def secure_mail_detail(request, pk):
    station = request.membership.station
    mail = get_object_or_404(SecureMail, pk=pk, station=station)
    is_recipient = SecureMailRecipient.objects.filter(mail=mail, user=request.user).exists()
    if mail.sender_id != request.user.id and not is_recipient:
        # Master-Admin and others must not read foreign mail.
        raise Http404
    if is_recipient:
        SecureMailRecipient.objects.filter(
            mail=mail, user=request.user, read_at__isnull=True
        ).update(read_at=timezone.now())
    envelope = serialize_message_for_client(mail, request.user.id)
    recipients = list(
        SecureMailRecipient.objects.filter(mail=mail).select_related("user")
    )
    return render(request, "core/secure_mail_detail.html", {
        "mail": mail,
        "envelope_json": json.dumps(envelope),
        "recipients": recipients,
        "has_keys": _require_crypto(request.user) is not None,
        "viewer_id": request.user.id,
    })
