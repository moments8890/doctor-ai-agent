"""Add project root to sys.path so tests in train/ can import project modules."""
import sys
import os

# Insert the project root (parent of this file's directory) at the front
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
