#!/usr/bin/env python3
"""WSGI entrypoint para o app Flask com suporte ao Indica Aqui."""
import os
import sys

# Garante que o diretório do app está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
