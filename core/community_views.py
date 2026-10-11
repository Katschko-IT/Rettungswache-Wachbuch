"""Registration, personal account area, and station chat."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access import CONTENT_ROLES, get_membership, membership_required, station_module_required
from .avatars import initials_for
from .forms import AvatarForm, ChatMessageForm, ProfileForm, RegistrationForm
from .models import ChatMessage, Membership, RegistrationRequest, UserProfile
from .rate_limit import consume as rate_limit_consume
from .services import audit, revoke_api_tokens_for_user


def registration_enabled():
    return bool(getattr(settings, "REGISTRATION_ENABLED", False))


def _client_ip(request):
    return getattr(request, "client_ip", "") or "unknown"


def _registration_rate_limited(request):
    ip = _client_ip(request)
    return not rate_limit_consume(
        "register",
        ip,
        limit=int(getattr(settings, "REGISTRATION_RATE_LIMIT", 5) or 5),
        window_seconds=3600,
    )


def _can_view_avatar(viewer, target_user):
    if viewer.id == target_user.id:
        return True
    viewer_membership = get_membership(viewer)
    target_membership = get_membership(target_user)
    return bool(
        viewer_membership
        and target_membership
        and viewer_membership.station_id == target_membership.station_id
    )


@require_http_methods(["GET", "POST"])
def register(request):
    if not registration_enabled():
        raise Http404
    if request.user.is_authenticated:
        return redirect("landing")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _registration_rate_limited(request):
            messages.error(request, "Zu viele Registrierungen von dieser Adresse. Bitte später erneut versuchen.")
            return render(request, "registration/register.html", {"form": form})
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password1"],
                first_name=form.cleaned_data.get("first_name") or "",
            )
            UserProfile.for_user(user)
            RegistrationRequest.objects.create(
                user=user,
                preferred_station=form.cleaned_data["preferred_station"],
                note=form.cleaned_data.get("note") or "",
            )
            audit(user, form.cleaned_data["preferred_station"], "registration.submitted", user, {
                "fields": ["username", "preferred_station"],
            })
        messages.success(
            request,
            "Konto angelegt. Nach der Anmeldung freigibt der Master-Admin den Wachenzugang.",
        )
        return redirect("login")
    return render(request, "registration/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def account_home(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={reverse('account_home')}")
    membership = get_membership(request.user)
    registration = RegistrationRequest.objects.filter(user=request.user).first()
    profile = UserProfile.for_user(request.user)
    action = request.POST.get("action") if request.method == "POST" else None
    avatar_form = AvatarForm(prefix="avatar")
    if action == "password" and getattr(settings, "DEMO_PUBLIC_MODE", False):
        # Shared demo accounts must keep one documented password for every
        # visitor, so the public demo never allows changing it.
        messages.error(
            request,
            "Im öffentlichen Demo-Modus kann das Passwort nicht geändert werden.",
        )
        return redirect("account_home")
    if action == "profile":
        profile_form = ProfileForm(request.POST, instance=request.user, prefix="profile")
        password_form = PasswordChangeForm(request.user, prefix="password")
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, "Profil wurde gespeichert.")
            return redirect("account_home")
    elif action == "password":
        profile_form = ProfileForm(instance=request.user, prefix="profile")
        password_form = PasswordChangeForm(request.user, request.POST, prefix="password")
        if password_form.is_valid():
            user = password_form.save()
            revoked = revoke_api_tokens_for_user(user)
            update_session_auth_hash(request, user)
            if revoked:
                audit(user, membership.station if membership else None, "api.tokens_revoked_password", user, {
                    "fields": ["is_active"],
                    "count": revoked,
                })
                messages.success(
                    request,
                    "Passwort wurde geändert. Alle App-Tokens wurden widerrufen – bitte neu erzeugen.",
                )
            else:
                messages.success(request, "Passwort wurde geändert.")
            return redirect("account_home")
    elif action == "avatar":
        profile_form = ProfileForm(instance=request.user, prefix="profile")
        password_form = PasswordChangeForm(request.user, prefix="password")
        avatar_form = AvatarForm(request.POST, request.FILES, prefix="avatar")
        if avatar_form.is_valid():
            if avatar_form.cleaned_data.get("clear_avatar"):
                profile.avatar = None
                profile.avatar_content_type = ""
                profile.avatar_updated_at = None
                profile.save(update_fields=["avatar", "avatar_content_type", "avatar_updated_at", "updated_at"])
                audit(request.user, membership.station if membership else None, "profile.avatar_cleared", request.user, {
                    "fields": ["avatar"],
                })
                messages.success(request, "Profilbild wurde entfernt.")
            else:
                profile.avatar = avatar_form.cleaned_data["avatar_bytes"]
                profile.avatar_content_type = avatar_form.cleaned_data["avatar_content_type"]
                profile.avatar_updated_at = timezone.now()
                profile.save(update_fields=["avatar", "avatar_content_type", "avatar_updated_at", "updated_at"])
                audit(request.user, membership.station if membership else None, "profile.avatar_updated", request.user, {
                    "fields": ["avatar"],
                })
                messages.success(request, "Profilbild wurde gespeichert.")
            return redirect("account_home")
    else:
        profile_form = ProfileForm(instance=request.user, prefix="profile")
        password_form = PasswordChangeForm(request.user, prefix="password")
    return render(request, "core/account.html", {
        "profile_form": profile_form,
        "password_form": password_form,
        "avatar_form": avatar_form,
        "profile": profile,
        "initials": initials_for(request.user),
        "membership": membership,
        "registration": registration,
    })


@require_GET
def avatar_image(request, user_id):
    if not request.user.is_authenticated:
        raise Http404
    target = get_object_or_404(User, pk=user_id, is_active=True)
    if not _can_view_avatar(request.user, target):
        raise Http404
    profile = UserProfile.objects.filter(user=target).first()
    if not profile or not profile.avatar:
        raise Http404
    response = HttpResponse(bytes(profile.avatar), content_type=profile.avatar_content_type or "image/jpeg")
    response["Cache-Control"] = "private, max-age=300"
    return response


@membership_required(CONTENT_ROLES)
@station_module_required("chat_enabled")
@require_http_methods(["GET", "POST"])
def chat(request):
    import json

    from .messaging import public_keys_for_users, serialize_message_for_client, station_content_users, validate_encrypted_payload
    from .models import UserCryptoIdentity

    station = request.membership.station
    identity = UserCryptoIdentity.objects.filter(user=request.user).first()
    if request.method == "POST" and request.headers.get("Content-Type", "").startswith("application/json"):
        if not identity:
            return JsonResponse({"ok": False, "error": "Bitte zuerst Schlüssel unter Mein Konto einrichten."}, status=400)
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"ok": False, "error": "Ungültige Anfrage."}, status=400)
        members = list(station_content_users(station))
        keyed_ids = set(
            UserCryptoIdentity.objects.filter(user__in=members).values_list("user_id", flat=True)
        )
        # Encrypt for everyone who already has keys, always including author.
        required = set(keyed_ids) | {request.user.id}
        if request.user.id not in keyed_ids:
            return JsonResponse({"ok": False, "error": "Eigene Schlüssel fehlen."}, status=400)
        from django.core.exceptions import ValidationError

        try:
            payload = validate_encrypted_payload(body, required_recipient_ids=required)
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": " ".join(exc.messages)}, status=400)
        message = ChatMessage.objects.create(
            station=station,
            author=request.user,
            body="",
            ciphertext=payload["ciphertext"],
            nonce=payload["nonce"],
            key_wraps=payload["key_wraps"],
            algo=payload["algo"],
            is_encrypted=True,
        )
        audit(request.user, station, "chat.message_created", message, {
            "fields": ["ciphertext"],
            "encrypted": True,
        })
        return JsonResponse({"ok": True, "id": message.pk})

    # Legacy plaintext form path disabled for new posts when crypto is expected.
    form = ChatMessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        messages.error(
            request,
            "Neue Wachenchats sind Ende-zu-Ende-verschlüsselt. Bitte JavaScript nutzen bzw. Schlüssel einrichten.",
        )
        return redirect("chat")

    page = (
        ChatMessage.objects.filter(station=station, is_hidden=False)
        .select_related("author")[:80]
    )
    thread = list(reversed(list(page)))
    profile_map = {
        profile.user_id: profile
        for profile in UserProfile.objects.filter(user_id__in={item.author_id for item in thread})
    }
    feed = []
    client_feed = []
    for item in thread:
        profile = profile_map.get(item.author_id)
        feed.append({
            "message": item,
            "initials": initials_for(item.author),
            "has_avatar": bool(profile and profile.has_avatar),
            "is_own": item.author_id == request.user.id,
            "envelope": serialize_message_for_client(item, request.user.id),
        })
        client_feed.append({
            **serialize_message_for_client(item, request.user.id),
            "author_name": item.author.first_name or item.author.username,
            "initials": initials_for(item.author),
            "has_avatar": bool(profile and profile.has_avatar),
            "is_own": item.author_id == request.user.id,
        })
    members = public_keys_for_users(station_content_users(station))
    return render(request, "core/chat.html", {
        "form": form,
        "feed": feed,
        "feed_json": json.dumps(client_feed),
        "members_json": json.dumps(members),
        "has_keys": identity is not None,
        "viewer_id": request.user.id,
        "can_moderate": request.membership.role in {
            Membership.Role.SHIFT_LEAD,
            Membership.Role.ADMIN,
        },
    })


@membership_required({Membership.Role.SHIFT_LEAD, Membership.Role.ADMIN})
@station_module_required("chat_enabled")
@require_POST
def chat_hide(request, pk):
    message = get_object_or_404(ChatMessage, pk=pk, station=request.membership.station)
    if not message.is_hidden:
        message.is_hidden = True
        message.save(update_fields=["is_hidden"])
        audit(request.user, request.membership.station, "chat.message_hidden", message, {
            "fields": ["is_hidden"],
            "changes": {"is_hidden": {"from": False, "to": True}},
        })
        messages.success(request, "Nachricht wurde ausgeblendet.")
    return redirect("chat")


@membership_required({Membership.Role.ADMIN})
@require_POST
def registration_reject(request, pk):
    item = get_object_or_404(
        RegistrationRequest,
        pk=pk,
        status=RegistrationRequest.Status.PENDING,
        preferred_station=request.membership.station,
    )
    item.status = RegistrationRequest.Status.REJECTED
    item.reviewed_at = timezone.now()
    item.reviewed_by = request.user
    item.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    item.user.is_active = False
    item.user.save(update_fields=["is_active"])
    audit(request.user, request.membership.station, "registration.rejected", item.user, {
        "fields": ["status"],
    })
    messages.success(request, "Registrierung wurde abgelehnt.")
    return redirect("team")
