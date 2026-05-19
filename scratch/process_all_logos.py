# process_all_logos.py
import os
from PIL import Image

def process_logos():
    src_path = 'photo_2026-04-19_00-04-43.jpg'
    icons_dir = 'cabinet/public/icons'
    os.makedirs(icons_dir, exist_ok=True)

    print("Opening source image...")
    img = Image.open(src_path)

    # 1. Save standard full-color PWA icons
    # icon-192x192.png
    print("Generating icon-192x192.png...")
    img_192 = img.resize((192, 192), Image.Resampling.LANCZOS)
    img_192.save(os.path.join(icons_dir, 'icon-192x192.png'), 'PNG')

    # icon-512x512.png
    print("Generating icon-512x512.png...")
    img_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
    img_512.save(os.path.join(icons_dir, 'icon-512x512.png'), 'PNG')

    # apple-touch-icon.png
    print("Generating apple-touch-icon.png...")
    img_apple = img.resize((180, 180), Image.Resampling.LANCZOS)
    img_apple.save(os.path.join(icons_dir, 'apple-touch-icon.png'), 'PNG')

    # Overwrite bot/vpn_logo.png with the new logo (512x512 PNG)
    print("Generating bot/vpn_logo.png...")
    img_512.save('bot/vpn_logo.png', 'PNG')

    # 2. Generate a custom transparent monochrome badge stencil for Android status bar
    print("Generating transparent monochrome badge-96x96.png...")
    img_badge = img.resize((96, 96), Image.Resampling.LANCZOS)
    rgba_badge = img_badge.convert('RGBA')
    
    # Process pixels to create a perfect transparent monochrome silhouette
    pixels = rgba_badge.load()
    for y in range(rgba_badge.height):
        for x in range(rgba_badge.width):
            r, g, b, a = pixels[x, y]
            # Calculate luminance
            L = 0.299 * r + 0.587 * g + 0.114 * b
            
            # If brightness is low (dark background), make it transparent
            if L < 35:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                # Smooth alpha transition for anti-aliasing
                alpha = int(min(255, max(0, (L - 35) * 255 / (255 - 35))))
                pixels[x, y] = (255, 255, 255, alpha)

    rgba_badge.save(os.path.join(icons_dir, 'badge-96x96.png'), 'PNG')
    rgba_badge.save(os.path.join(icons_dir, 'badge.png'), 'PNG')
    print("All PWA icons and badge stencil generated successfully!")

if __name__ == '__main__':
    process_logos()
