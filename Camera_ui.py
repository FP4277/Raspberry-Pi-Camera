#!/usr/bin/env python3
import os
import sys
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from picamera2 import Picamera2
from displayhatmini import DisplayHATMini

# Constants
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
PHOTO_DIR = os.path.expanduser("~/Desktop/Camera")
BACKLIGHT_FULL = 1.0
BACKLIGHT_DIM = 0.2
IDLE_TIMEOUT = 70  # seconds

# Button mappings
BUTTON_A = DisplayHATMini.BUTTON_A  # Top-left
BUTTON_B = DisplayHATMini.BUTTON_B  # Top-right
BUTTON_X = DisplayHATMini.BUTTON_X  # Bottom-left
BUTTON_Y = DisplayHATMini.BUTTON_Y  # Bottom-right

display_image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
draw = ImageDraw.Draw(display_image)
display = DisplayHATMini(display_image)
display.set_backlight(BACKLIGHT_FULL)

# Create photo directory
os.makedirs(PHOTO_DIR, exist_ok=True)

# Font
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except:
    font = ImageFont.load_default()


class ButtonHandler:
    def __init__(self, callback):
        self.callback = callback
        self.pressed = {}
        self.lock = threading.Lock()
        self.polling = True
        self.thread = threading.Thread(target=self.poll_buttons)
        self.thread.start()

    def poll_buttons(self):
        while self.polling:
            for label, pin in {'A': BUTTON_A, 'B': BUTTON_B, 'X': BUTTON_X, 'Y': BUTTON_Y}.items():
                current = display.read_button(pin)
                prev = self.pressed.get(label, False)

                if current and not prev:
                    self.press_start[label] = time.monotonic()

                if not current and prev:
                    duration = time.monotonic() - self.press_start.get(label, 0)
                    self.callback(label, duration > 1.0)

                self.pressed[label] = current

            time.sleep(0.05)

    def stop(self):
        self.polling = False
        self.thread.join()

    press_start = {}


class CameraUI:
    def __init__(self):
        self.last_interaction = time.monotonic()
        self.mode = "photo"
        self.capture_preview = True
        self.last_photo_path = None
        self.picam2 = Picamera2()
        self.configure_camera()

        self.buttons = ButtonHandler(self.handle_button)

        self.preview_thread = threading.Thread(target=self.preview_loop)
        self.preview_thread.daemon = True
        self.preview_thread.start()

    def configure_camera(self):
        # Setup camera with preview config
        cfg = self.picam2.create_preview_configuration(
            main={"size": (640, 480)}
        )
        self.picam2.configure(cfg)
        self.picam2.set_controls({"AfMode": 2})  # Continuous autofocus
        self.picam2.start()

    def preview_loop(self):
        while True:
            now = time.monotonic()

            if now - self.last_interaction > IDLE_TIMEOUT:
                display.set_backlight(BACKLIGHT_DIM)
            else:
                display.set_backlight(BACKLIGHT_FULL)

            if self.capture_preview:
                try:
                    frame = self.picam2.capture_array(resolution="main")
                    self.draw_frame(Image.fromarray(frame))
                except Exception as e:
                    continue

            time.sleep(0.1)

    def draw_frame(self, frame):
        frame = frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        display_image.paste(frame)

        draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
        draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))

        display.display()

    def capture_photo(self):
        filename = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
        full_path = os.path.join(PHOTO_DIR, filename)

        self.picam2.set_controls({"AfMode": 2})  # Ensure AF is enabled
        time.sleep(0.15)

        self.picam2.capture_file(full_path)
        self.last_photo_path = full_path
        self.flash_ui("✓")

    def flash_ui(self, icon):
        draw.rectangle((300, 0, 319, 19), fill=(255, 255, 255))
        draw.text((305, 2), icon, font=font, fill=(0, 0, 0))
        display.display()
        time.sleep(0.5)

    def view_last_photo(self):
        if self.last_photo_path and os.path.exists(self.last_photo_path):
            img = Image.open(self.last_photo_path).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
            display_image.paste(img)
            draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
            draw.text((5, 2), "Last Photo", font=font, fill=(255, 255, 255))
            display.display()
            time.sleep(3)

    def toggle_preview(self):
        self.capture_preview = not self.capture_preview
        if not self.capture_preview:
            display.set_backlight(BACKLIGHT_DIM)
        else:
            self.flash_ui("▶")

    def handle_button(self, label, long_press):
        self.last_interaction = time.monotonic()

        if label == 'A' and not long_press:
            self.capture_photo()
        elif label == 'A' and long_press:
            self.toggle_preview()
        elif label == 'B' and not long_press:
            self.view_last_photo()
        elif label == 'B' and long_press:
            self.mode = "settings" if self.mode == "photo" else "photo"
        elif label == 'X' and long_press:
            self.picam2.set_controls({"AfTrigger": 0})  # Trigger focus
            self.flash_ui("AF")

        elif label == 'Y' and long_press:
            self.safe_shutdown()

    def safe_shutdown(self):
        self.flash_ui("OFF")
        draw.rectangle((0, 0, 320, 240), fill=(0, 0, 0))
        draw.text((60, 110), "Powering off...", font=font, fill=(255, 0, 0))
        display.display()
        os.system("sudo shutdown now")

    def stop(self):
        self.buttons.stop()
        self.picam2.stop()
        display.set_backlight(0)


if __name__ == "__main__":
    ui = CameraUI()
    print("Camera UI running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        ui.stop()
