#!/usr/bin/env python3
"""WSGI entrypoint para o app Flask com suporte ao Indica Aqui."""
import os
import sys

# Garante que o diretório do app está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

# Route Dump for verification
print("--- DEBUG: Registered Routes ---", flush=True)
for rule in app.url_map.iter_rules():
    print(f"Endpoint: {rule.endpoint:<25} Methods: {','.join(rule.methods):<20} Path: {rule.rule}", flush=True)
print("--------------------------------", flush=True)
