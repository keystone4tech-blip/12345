# inspect_image.py
import sys
from PIL import Image

try:
    img = Image.open('photo_2026-04-19_00-04-43.jpg')
    print(f"Format: {img.format}")
    print(f"Size: {img.size}")
    print(f"Mode: {img.mode}")
except Exception as e:
    print(f"Error: {e}")
