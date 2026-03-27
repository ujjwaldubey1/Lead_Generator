"""Outreach helpers for phase 4 of the pipeline."""

from .email_finder import find_email
from .email_writer import generate_email
from .instantly_client import add_lead_to_campaign

__all__ = ["find_email", "generate_email", "add_lead_to_campaign"]

