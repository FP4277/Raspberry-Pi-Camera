from displayhatmini import DisplayHATMini
from PIL import Image, ImageDraw
import time

# Create a buffer (same size as screen)
WIDTH = 320
HEIGHT = 240
buffer = Image.new("RGB", (WIDTH, HEIGHT))
draw = ImageDraw.Draw(buffer)

# Pass the buffer to DisplayHATMini
display = DisplayHATMini(buffer)
display.set_backlight(1.0)  # full brightness

# Draw to buffer
draw.rectangle((0, 0, WIDTH, HEIGHT), fill="darkgreen")
draw.text((80, 110), "Display Works!", fill="white")

# Show it!
display.display()

# Keep it on screen for a few seconds
print("✓ Display is ON. You should see green with text.")
time.sleep(5)

# Optional: fade out
display.set_backlight(0)
