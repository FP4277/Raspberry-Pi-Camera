#!/usr/bin/env python3
import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from picamera2 import Picamera2
from displayhatmini import DisplayHATMini

# Constants
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
PHOTO_DIR = os.path.expanduser("~/Desktop/Camera")
BACKLIGHT_BRIGHT = 1.0
BACKLIGHT_DIM = 0.25
IDLE_TIMEOUT = 70  # seconds
DOUBLE_PRESS_WINDOW = 0.35  # Max time for double press

# Buttons - remap based on physical layout: A top-left, B bottom-left, X top-right, Y bottom-right
BUTTON_MAP = {
    'A': DisplayHATMini.BUTTON_A,  # Top-left
    'B': DisplayHATMini.BUTTON_B,  # Bottom-left
    'X': DisplayHATMini.BUTTON_X,  # Top-right
    'Y': DisplayHATMini.BUTTON_Y   # Bottom-right
}

display_image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
draw = ImageDraw.Draw(display_image)
display = DisplayHATMini(display_image)
display.set_backlight(BACKLIGHT_BRIGHT)
os.makedirs(PHOTO_DIR, exist_ok=True)

# Load font
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except:
    font = ImageFont.load_default()

class ButtonHandler:
    def __init__(self, callback):
        self.callback = callback
        self.btn_state = {k: False for k in BUTTON_MAP}
        self.last_press_time = {}
        self.running = True
        self.thread = threading.Thread(target=self.listen)
        self.thread.start()

    def listen(self):
        while self.running:
            for label, pin in BUTTON_MAP.items():
                pressed = display.read_button(pin)
                if pressed and not self.btn_state[label]:
                    now = time.monotonic()

                    if label in self.last_press_time and now - self.last_press_time[label] <= DOUBLE_PRESS_WINDOW:
                        self.callback(label, double=True)
                        self.last_press_time[label] = 0
                    else:
                        self.last_press_time[label] = now

                    self.btn_state[label] = True

                elif not pressed and self.btn_state[label]:
                    if self.last_press_time[label] != 0:
                        if time.monotonic() - self.last_press_time[label] > DOUBLE_PRESS_WINDOW:
                            self.callback(label, double=False)
                    self.btn_state[label] = False

            time.sleep(0.05)

    def stop(self):
        self.running = False
        self.thread.join()

class CameraUI:
    def __init__(self):
        self.last_interaction = time.monotonic()
        self.mode = 'photo'
        self.preview_enabled = True
        self.last_photo_path = None
        self.viewing = False
        self.settings_index = 0
        self.settings_items = ['ISO (future)', 'Shutter (future)', 'White Balance (future)']

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 480)}, display="main")
        self.picam2.configure(config)
        self.picam2.set_controls({"AfMode": 2})
        self.picam2.start()

        self.button_handler = ButtonHandler(self.handle_button)
        self.preview_thread = threading.Thread(target=self.preview_loop, daemon=True)
        self.preview_thread.start()

    def preview_loop(self):
        while True:
            now = time.monotonic()
            if now - self.last_interaction > IDLE_TIMEOUT:
                display.set_backlight(BACKLIGHT_DIM)
            else:
                display.set_backlight(BACKLIGHT_BRIGHT)

            if self.preview_enabled and not self.viewing:
                try:
                    frame = Image.fromarray(self.picam2.capture_array())
                    frame = frame.rotate(180)  # <--- Flip preview
                    frame = frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    display_image.paste(frame)

                    # Top bar
                    draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
                    draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))

                    # Show setting name in settings mode
                    if self.mode == 'settings':
                        current = self.settings_items[self.settings_index]
                        draw.rectangle((0, 200, 320, 240), fill=(0, 0, 0))
                        draw.text((5, 210), f"> {current}", font=font, fill=(255, 255, 0))

                    display.display()
                except:
                    pass
            time.sleep(0.1)

    def handle_button(self, label, double):
        self.last_interaction = time.monotonic()

        # Buttons are A (top-left), B (bottom-left), X (top-right), Y (bottom-right)

        if label == 'A':
            if double:
                self.toggle_preview()
            else:
                self.capture_photo()

        elif label == 'B':
            if double:
                self.toggle_mode()
            else:
                self.view_last_photo()

        elif label == 'X':
            if self.mode == 'settings':
                self.settings_index = (self.settings_index - 1) % len(self.settings_items)
            elif double:
                self.trigger_AF()

        elif label == 'Y':
            if self.mode == 'settings':
                self.settings_index = (self.settings_index + 1) % len(self.settings_items)
            elif double:
                self.power_off()

    def capture_photo(self):
        filename = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
        filepath = os.path.join(PHOTO_DIR, filename)
        self.picam2.set_controls({"AfMode": 2})
        time.sleep(0.1)
        self.picam2.capture_file(filepath)
        self.last_photo_path = filepath
        self.flash_ui("✓")

    def view_last_photo(self):
        if self.last_photo_path and os.path.exists(self.last_photo_path):
            self.viewing = True
            try:
                img = Image.open(self.last_photo_path).rotate(180).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                display_image.paste(img)
                draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
                draw.text((5, 2), "Last Photo - A to exit", font=font, fill=(255, 255, 255))
                display.display()

                while True:
                    if display.read_button(BUTTON_MAP['A']):
                        break
                    time.sleep(0.1)

                self.viewing = False
            except:
                self.viewing = False

    def toggle_preview(self):
        self.preview_enabled = not self.preview_enabled
        self.flash_ui("▶" if self.preview_enabled else "■")

    def toggle_mode(self):
        self.mode = 'settings' if self.mode == 'photo' else 'photo'
        self.flash_ui("⚙")

    def trigger_AF(self):
        self.picam2.set_controls({"AfTrigger": 0})
        self.flash_ui("AF")

    def power_off(self):
        self.flash_ui("OFF")
        draw.rectangle((0, 0, 320, 240), fill=(0, 0, 0))
        draw.text((60, 110), "Shutting down...", font=font, fill=(255, 0, 0))
        display.display()
        time.sleep(1)
        os.system("sudo shutdown now")

    def flash_ui(self, icon):
        draw.rectangle((280, 0, 319, 20), fill=(255, 255, 255))
        draw.text((285, 2), icon, font=font, fill=(0, 0, 0))
        display.display()
        time.sleep(0.4)

    def stop(self):
        self.picam2.stop()
        display.set_backlight(0)
        self.button_handler.stop()


if __name__ == "__main__":
    ui = CameraUI()
    print("Camera UI running. Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting camera...")
        ui.stop()
