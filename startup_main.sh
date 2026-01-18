#!/bin/bash
set -e

echo "Starting initialization setup..."
python init_setup.py

echo "Starting main application..."
python main.py
