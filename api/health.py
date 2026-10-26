"""Vercel 서버리스 함수: /api/health  (실제 처리는 carebridge/web.py)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from carebridge.web import app  # noqa: E402,F401
