"""Slack webhook helper for 3-channel alerting.

Reads webhook URLs from AWS SSM Parameter Store and caches them for the
lifetime of the process. Runs on EC2 (which has internet access) — NOT
called from Lambda.

Channels:
  - critical: /countyiq/slack-webhook-critical  (#alerts-critical)
  - warning:  /countyiq/slack-webhook-warning   (#alerts-warning)
  - pipeline: /countyiq/slack-webhook-pipeline   (#pipeline-runs)
"""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import requests
from dagster import get_dagster_logger

SLACK_SSM_PARAMS = {
    "critical": "/countyiq/slack-webhook-critical",
    "warning": "/countyiq/slack-webhook-warning",
    "pipeline": "/countyiq/slack-webhook-pipeline",
}

_webhook_cache: dict[str, str] = {}


def get_slack_webhook_url(channel: str = "pipeline") -> str | None:
    """Retrieve a Slack webhook URL from SSM Parameter Store (cached).

    Args:
        channel: One of 'critical', 'warning', 'pipeline'.

    Returns:
        The webhook URL, or None if SSM is unreachable (local dev).
    """
    if channel in _webhook_cache:
        return _webhook_cache[channel]

    # Allow override via env var for local testing
    env_key = f"SLACK_WEBHOOK_{channel.upper()}"
    env_val = os.environ.get(env_key)
    if env_val:
        _webhook_cache[channel] = env_val
        return env_val

    param_name = SLACK_SSM_PARAMS.get(channel)
    if not param_name:
        raise ValueError(f"Unknown Slack channel: {channel}. Use: {list(SLACK_SSM_PARAMS)}")

    log = get_dagster_logger()
    try:
        ssm = boto3.client("ssm", region_name="us-east-1")
        response = ssm.get_parameter(Name=param_name, WithDecryption=True)
        url = response["Parameter"]["Value"]
        _webhook_cache[channel] = url
        return url
    except (BotoCoreError, ClientError) as e:
        log.warning(f"Could not fetch Slack webhook from SSM ({param_name}): {e}")
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
