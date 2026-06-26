# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os

import frappe
from frappe.utils.password import decrypt, encrypt


SETTINGS_DOCTYPE = "Operations KPI Report Settings"


def get_openai_api_key(settings=None):
    if settings is None:
        settings = frappe.get_single(SETTINGS_DOCTYPE)
    encrypted_key = (settings.get("openai_api_key_encrypted") or "").strip()
    if encrypted_key:
        return (decrypt(encrypted_key) or "").strip()
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def has_openai_api_key(settings=None):
    return bool(get_openai_api_key(settings))


def store_openai_api_key(settings, api_key):
    api_key = (api_key or "").strip()
    settings.openai_api_key_encrypted = encrypt(api_key) if api_key else ""
    settings.openai_api_key = ""
    settings.openai_api_key_configured = int(bool(api_key))


def clear_openai_api_key(settings):
    settings.openai_api_key = ""
    settings.openai_api_key_encrypted = ""
    settings.openai_api_key_configured = 0
