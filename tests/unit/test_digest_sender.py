"""Unit tests for the DigestSender."""
import pytest
from unittest.mock import MagicMock, patch
from niche.core.email.digest_sender import DigestSender
from niche.core.email.dev_provider import DevEmailProvider


def make_fake_user(email="user@example.com", uid="user-1"):
    user = MagicMock()
    user.id = uid
    user.email = email
    return user


def make_fake_digest(date="2026-04-28", item_count=5):
    digest = MagicMock()
    digest.date = date
    digest.item_count = item_count
    return digest


def make_fake_bundle(feed_name="TestFeed", from_email="news@example.com"):
    bundle = MagicMock()
    bundle.config.name = feed_name
    bundle.config.from_email = from_email
    return bundle


def make_jinja_env_with_template(html="<html>Test digest</html>"):
    """Return a mock Jinja env that returns a template rendering fixed html."""
    template = MagicMock()
    template.render.return_value = html
    env = MagicMock()
    env.get_template.return_value = template
    return env


def test_send_to_user_success():
    provider = DevEmailProvider()
    env = make_jinja_env_with_template()
    sender = DigestSender(
        email_provider=provider,
        jinja_env=env,
        app_url="https://example.com",
        feed_id="test-fixture",
    )
    user = make_fake_user()
    digest = make_fake_digest()
    bundle = make_fake_bundle()
    ok = sender.send_to_user(user, digest, [], bundle, unsubscribe_token="tok123")
    assert ok is True


def test_send_to_user_template_missing():
    """If template is missing, send_to_user returns False without raising."""
    provider = DevEmailProvider()
    env = MagicMock()
    env.get_template.side_effect = Exception("Template not found")
    sender = DigestSender(
        email_provider=provider,
        jinja_env=env,
        app_url="https://example.com",
        feed_id="test-fixture",
    )
    user = make_fake_user()
    digest = make_fake_digest()
    bundle = make_fake_bundle()
    ok = sender.send_to_user(user, digest, [], bundle, unsubscribe_token="tok123")
    assert ok is False


def test_send_to_user_provider_failure_retries_and_returns_false():
    """If provider always fails, send_to_user exhausts retries and returns False."""
    failing_provider = MagicMock()
    failing_provider.send.side_effect = Exception("SMTP error")
    env = make_jinja_env_with_template()
    sender = DigestSender(
        email_provider=failing_provider,
        jinja_env=env,
        app_url="https://example.com",
        feed_id="test-fixture",
    )
    user = make_fake_user()
    digest = make_fake_digest()
    bundle = make_fake_bundle()
    ok = sender.send_to_user(user, digest, [], bundle, unsubscribe_token="tok123")
    assert ok is False
    # Should have attempted MAX_RETRIES + 1 times
    assert failing_provider.send.call_count == DigestSender.MAX_RETRIES + 1


def test_subject_includes_date_and_item_count():
    """Email subject should contain the digest date and item count."""
    sent_subjects = []

    class CapturingProvider:
        def send(self, to, subject, html_body, from_email, **kwargs):
            sent_subjects.append(subject)
            return True

    env = make_jinja_env_with_template()
    sender = DigestSender(
        email_provider=CapturingProvider(),
        jinja_env=env,
        app_url="https://example.com",
        feed_id="test-fixture",
    )
    items = [MagicMock() for _ in range(7)]
    user = make_fake_user()
    digest = make_fake_digest(date="2026-04-28")
    bundle = make_fake_bundle(feed_name="TestFeed")
    sender.send_to_user(user, digest, items, bundle, unsubscribe_token="tok")
    assert len(sent_subjects) == 1
    assert "2026-04-28" in sent_subjects[0]
    assert "7" in sent_subjects[0]
