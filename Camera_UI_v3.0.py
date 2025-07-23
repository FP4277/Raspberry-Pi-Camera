#!/usr/bin/env python3
import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from picamera2 import Picamera2
from displayhatmini import DisplayHATMini
import glob

# Constants
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
PHOTO_DIR = os.path.expanduser("~/Desktop/Camera")
BACKLIGHT_BRIGHT = 1.0
BACKLIGHT_DIM = 0.25
IDLE_TIMEOUT = 70
DOUBLE_PRESS_WINDOW = 0.45  # Adjusted for better realism

BUTTON_MAP = {
    'A': DisplayHATMini.BUTTON_A,
    'B': DisplayHATMini.BUTTON_B,
    'X': DisplayHATMini.BUTTON_X,
    'Y': DisplayHATMini.BUTTON_Y
}

display_image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
draw = ImageDraw.Draw(display_image)
display = DisplayHATMini(display_image)
display.set_backlight(BACKLIGHT_BRIGHT)
os.makedirs(PHOTO_DIR, exist_ok=True)

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except:
    font = ImageFont.load_default()


class ButtonHandler:
    def __init__(self, callback):
        self.callback = callback
        self.btn_state = {k: False for k in BUTTON_MAP}
        self.last_press = {}
        self.running = True
        self.thread = threading.Thread(target=self.poll)
        self.thread.start()

    def poll(self):
        while self.running:
            for label, pin in BUTTON_MAP.items():
                pressed = display.read_button(pin)
                if pressed and not self.btn_state[label]:
                    now = time.monotonic()
                    if label in self.last_press and now - self.last_press[label] < DOUBLE_PRESS_WINDOW:
                        self.callback(label, double=True)
                        self.last_press[label] = 0
                    else:
                        self.last_press[label] = now
                    self.btn_state[label] = True
                elif not pressed and self.btn_state[label]:
                    if self.last_press.get(label, 0) != 0:
                        if time.monotonic() - self.last_press[label] >= DOUBLE_PRESS_WINDOW:
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
        self.viewing = False
        self.current_photo_index = -1
        self.gallery_list = []

        self.iso = 100
        self.brightness = 1.0
        self.af_mode = True
        self.settings_index = 0
        self.settings_items = ['ISO', 'Brightness', 'Focus Mode']

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 480)}, display="main")
        self.picam2.configure(config)
        self.apply_settings()
        self.picam2.start()

        self.buttons = ButtonHandler(self.handle_button)
        self.preview_thread = threading.Thread(target=self.preview_loop, daemon=True)
        self.preview_thread.start()

    def apply_settings(self):
        self.picam2.set_controls({
            "AfMode": 2 if self.af_mode else 0,
            "AnalogueGain": self.iso / 100.0
        })

    def preview_loop(self):
        while True:
            now = time.monotonic()
            idle = now - self.last_interaction > IDLE_TIMEOUT
            display.set_backlight(BACKLIGHT_DIM if idle else BACKLIGHT_BRIGHT)

            if self.preview_enabled and not self.viewing:
                try:
                    frame = Image.fromarray(self.picam2.capture_array()).rotate(180)
                    frame = ImageEnhance.Brightness(frame).enhance(self.brightness)
                    frame = frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    display_image.paste(frame)

                    # Top bar
                    draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
                    draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))
                    draw.text((280, 2), "AF" if self.af_mode else "MF", font=font, fill=(255, 255, 255))

                    # Settings UI
                    if self.mode == 'settings':
                        item = self.settings_items[self.settings_index]
                        val = self.get_value(item)
                        draw.rectangle((0, 200, 320, 240), fill=(0, 0, 0))
                        draw.text((5, 210), f"{item}: {val}", font=font, fill=(255, 255, 0))

                    display.display()
                except:
                    pass
            time.sleep(0.1)

    def get_value(self, setting):
        if setting == 'ISO':
            return str(self.iso)
        elif setting == 'Brightness':
            return f"{int(self.brightness * 100)}%"
        elif setting == 'Focus Mode':
            return "AF" if self.af_mode else "MF"
        return "-"

    def handle_button(self, label, double):
        now = time.monotonic()

        # Wake from sleep
        if now - self.last_interaction > IDLE_TIMEOUT and not double and label in ['X', 'Y']:
            self.last_interaction = now
            return

        self.last_interaction = now

        if self.viewing:
            self.handle_gallery_button(label)
            return

        if label == 'A':
            if double:
                self.toggle_preview()
            else:
                self.capture_photo()

        elif label == 'B':
            if double:
                self.toggle_mode()
            else:
                self.start_gallery()

        elif label == 'X':
            if self.mode == 'settings' and not double:
                self.settings_index = (self.settings_index - 1) % len(self.settings_items)
            elif self.mode == 'settings' and double:
                self.adjust_setting()
            elif self.mode != 'settings' and double:
                self.toggle_af()

        elif label == 'Y':
            if self.mode == 'settings' and not double:
                self.settings_index = (self.settings_index + 1) % len(self.settings_items)
            elif self.mode == 'settings' and double:
                self.adjust_setting()
            elif double:
                self.shutdown()

    def start_gallery(self):
        self.gallery_list = sorted(glob.glob(os.path.join(PHOTO_DIR, '*.jpg')))
        if self.gallery_list:
            self.current_photo_index = len(self.gallery_list) - 1
            self.viewing = True
            self.show_current_photo()

    def handle_gallery_button(self, label):
        if label == 'A':
            self.viewing = False
        elif label == 'X':
            self.current_photo_index = max(0, self.current_photo_index - 1)
            self.show_current_photo()
        elif label == 'Y':
            self.current_photo_index = min(len(self.gallery_list) - 1, self.current_photo_index + 1)
            self.show_current_photo()

    def show_current_photo(self):
        try:
            img_path = self.gallery_list[self.current_photo_index]
            img = Image.open(img_path).rotate(180).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
            display_image.paste(img)
            draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
            draw.text((5, 2), f"Viewing {self.current_photo_index+1}/{len(self.gallery_list)}", font=font, fill=(255, 255, 255))
            display.display()
        except:
            self.flash_icon("X")
            self.viewing = False

    def adjust_setting(self):
        item = self.settings_items[self.settings_index]
        if item == 'ISO':
            self.iso += 50
            if self.iso > 800:
                self.iso = 50
        elif item == 'Brightness':
            self.brightness += 0.1
            if self.brightness > 1.5:
                self.brightness = 0.5
        elif item == 'Focus Mode':
            self.af_mode = not self.af_mode
        self.apply_settings()

    def capture_photo(self):
        try:
            filename = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
            path = os.path.join(PHOTO_DIR, filename)
            self.picam2.capture_file(path)
            self.last_photo = path
            self.flash_icon("✓")
        except:
            self.flash_icon("X")

    def toggle_af(self):
        self.af_mode = not self.af_mode
        self.apply_settings()
        self.flash_icon("AF" if self.af_mode else "MF")

    def toggle_preview(self):
        self.preview_enabled = not self.preview_enabled
        self.flash_icon("▶" if self.preview_enabled else "■")

    def toggle_mode(self):
        self.mode = "settings" if self.mode == "photo" else "photo"
        self.settings_index = 0
        self.flash_icon("⚙")

    def flash_icon(self, icon):
        draw.rectangle((285, 0, 319, 20), fill=(255, 255, 255))
        draw.text((290, 2), icon, font=font, fill=(0, 0, 0))
        display.display()
        time.sleep(0.4)

    def shutdown(self):
        self.flash_icon("OFF")
        draw.rectangle((0, 0, 320, 240), fill=(0, 0, 0))
        draw.text((60, 110), "Shutting down...", font=font, fill=(255, 0, 0))
        display.display()
        time.sleep(1)
        os.system("sudo shutdown now")

    def stop(self):
        self.picam2.stop()
        self.buttons.stop()
        display.set_backlight(0)


if __name__ == "__main__":
    ui = CameraUI()
    print("Camera running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Goodbye!")
        ui.stop()
