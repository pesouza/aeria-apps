#!/usr/bin/env python3
"""Entrypoint para o app Flask com suporte ao Indica Aqui."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
