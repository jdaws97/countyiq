"""Optional Slack webhook notifications for pipeline run outcomes."""

import os

import requests
from dagster import get_dagster_logger

SLACK_CHANNELS = {"critical", "warning", "pipeline"}

_webhook_cache: dict[str, str] = {}


def get_slack_webhook_url(channel: str = "pipeline") -> str | None:
    """Return an environment-configured webhook URL, if present."""
    if channel not in SLACK_CHANNELS:
        raise ValueError(f"Unknown Slack channel: {channel}")
    if channel in _webhook_cache:
        return _webhook_cache[channel]

    env_key = f"SLACK_WEBHOOK_{channel.upper()}"
    env_val = os.environ.get(env_key)
    if env_val:
        _webhook_cache[channel] = env_val
        return env_val
    return None


def send_slack_message(channel: str, text: str, emoji: str = ":bell:"):
    """Post a message to a Slack channel via incoming webhook.

    Args:
        channel: One of 'critical', 'warning', 'pipeline'.
        text: Message text (supports Slack mrkdwn formatting).
        emoji: Slack emoji for the bot avatar.
    """
    log = get_dagster_logger()
    webhook_url = get_slack_webhook_url(channel)

    if not webhook_url:
        log.warning(f"Slack message not sent (no webhook for '{channel}'): {text[:100]}")
        return

    payload = {
        "username": "CountyIQ",
        "icon_emoji": emoji,
        "text": text,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning(f"Slack post failed ({channel}): {e}")
