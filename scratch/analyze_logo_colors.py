# analyze_logo_colors.py
from PIL import Image
from collections import Counter

img = Image.open('photo_2026-04-19_00-04-43.jpg')
# Sample the four corners to see what the background color is
corners = [
    img.getpixel((0, 0)),
    img.getpixel((0, img.height - 1)),
    img.getpixel((img.width - 1, 0)),
    img.getpixel((img.width - 1, img.height - 1))
]
print("Corners:", corners)

# Sample a 10x10 block from the top left corner to be sure
sample = []
for x in range(10):
    for y in range(10):
        sample.append(img.getpixel((x, y)))
common = Counter(sample).most_common(3)
print("Top-left 10x10 most common colors:", common)
