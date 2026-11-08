"""Vercel entry point: exposes the Dash app's Flask server as the WSGI callable `app`."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from app import server as app  # noqa: E402  (Flask object that Vercel serves)
