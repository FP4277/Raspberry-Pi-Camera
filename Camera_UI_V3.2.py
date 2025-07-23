#!/usr/bin/env python3
import os
import time
import threading
import glob
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from picamera2 import Picamera2
from displayhatmini import DisplayHATMini

# Constants
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
PHOTO_DIR = os.path.expanduser("~/Desktop/Camera")
os.makedirs(PHOTO_DIR, exist_ok=True)

BACKLIGHT_BRIGHT = 1.0
BACKLIGHT_DIM = 0.25
IDLE_TIMEOUT = 70  # seconds
DOUBLE_PRESS_WINDOW = 0.4

BUTTONS = {
    'A': DisplayHATMini.BUTTON_A,
    'B': DisplayHATMini.BUTTON_B,
    'X': DisplayHATMini.BUTTON_X,
    'Y': DisplayHATMini.BUTTON_Y
}

display_image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
draw = ImageDraw.Draw(display_image)
display = DisplayHATMini(display_image)
display.set_backlight(BACKLIGHT_BRIGHT)

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except:
    font = ImageFont.load_default()


class ButtonHandler:
    def __init__(self, callback):
        self.callback = callback
        self.state = {k: False for k in BUTTONS}
        self.last_press = {}
        self.running = True
        threading.Thread(target=self.poll, daemon=True).start()

    def poll(self):
        while self.running:
            for btn, pin in BUTTONS.items():
                pressed = display.read_button(pin)
                if pressed and not self.state[btn]:
                    now = time.monotonic()
                    if btn in self.last_press and now - self.last_press[btn] < DOUBLE_PRESS_WINDOW:
                        self.callback(btn, double=True)
                        self.last_press[btn] = 0
                    else:
                        self.last_press[btn] = now
                    self.state[btn] = True
                elif not pressed and self.state[btn]:
                    if self.last_press.get(btn, 0):
                        if time.monotonic() - self.last_press[btn] >= DOUBLE_PRESS_WINDOW:
                            self.callback(btn, double=False)
                    self.state[btn] = False
            time.sleep(0.05)

    def stop(self):
        self.running = False


class CameraUI:
    def __init__(self):
        # State variables
        self.mode = "photo"
        self.preview_enabled = True
        self.viewing = False
        self.last_interaction = time.monotonic()
        self.current_photo_idx = 0

        # Camera settings
        self.brightness = 1.0
        self.iso = 100
        self.shutter_speed = 10000
        self.af_mode = True
        self.control_mode = "auto"  # or "manual"

        self.settings_index = 0
        self.settings_items = [
            "Brightness",
            "Focus Mode",
            "Control Mode",
            "ISO",
            "Shutter Speed",
            "Profile"
        ]

        self.profiles = {
            "Daylight": {"iso": 100, "shutter": 10000, "brightness": 1.0, "af_mode": True},
            "Low Light": {"iso": 400, "shutter": 250000, "brightness": 1.3, "af_mode": False},
            "Indoors": {"iso": 200, "shutter": 50000, "brightness": 1.1, "af_mode": True}
        }
        self.profile_names = list(self.profiles.keys())
        self.current_profile = 0

        # Camera
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 480)})
        self.picam2.configure(config)
        self.apply_settings()
        self.picam2.start()

        # Threads
        self.button_handler = ButtonHandler(self.handle_button)
        threading.Thread(target=self.preview_loop, daemon=True).start()

    def apply_settings(self):
        if self.control_mode == "auto":
            controls = {
                "AeEnable": True,
                "AwbEnable": True,
                "AfMode": 2
            }
        else:
            controls = {
                "AeEnable": False,
                "AwbEnable": True,
                "AfMode": 2 if self.af_mode else 0,
                "AnalogueGain": self.iso / 100.0,
                "ExposureTime": self.shutter_speed
            }
        self.picam2.set_controls(controls)

    def preview_loop(self):
        while True:
            idle = time.monotonic() - self.last_interaction > IDLE_TIMEOUT
            display.set_backlight(BACKLIGHT_DIM if idle else BACKLIGHT_BRIGHT)
            if self.preview_enabled and not self.viewing:
                try:
                    img = Image.fromarray(self.picam2.capture_array())
                    img = img.rotate(180)
                    img = ImageEnhance.Brightness(img).enhance(self.brightness)
                    img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    display_image.paste(img)

                    # Top status bar
                    draw.rectangle((0, 0, DISPLAY_WIDTH, 20), fill=(0, 0, 0))
                    draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))
                    draw.text((250, 2), f"{'AF' if self.af_mode else 'MF'}", font=font, fill=(255, 255, 0))

                    # Settings display
                    if self.mode == "settings":
                        item = self.settings_items[self.settings_index]
                        val = self.get_setting_value(item)
                        draw.rectangle((0, 200, 320, 240), fill=(0, 0, 0))
                        draw.text((5, 210), f"{item}: {val}", font=font, fill=(255, 255, 0))

                    display.display()

                except Exception as e:
                    print("Preview error:", e)
            time.sleep(0.1)

    def get_setting_value(self, item):
        if item == "Brightness":
            return f"{self.brightness:.1f}"
        elif item == "Focus Mode":
            return "AF" if self.af_mode else "MF"
        elif item == "Control Mode":
            return self.control_mode.upper()
        elif item == "ISO":
            return str(self.iso) if self.control_mode == "manual" else "AUTO"
        elif item == "Shutter Speed":
            return f"{self.shutter_speed // 1000}ms" if self.control_mode == "manual" else "AUTO"
        elif item == "Profile":
            return self.profile_names[self.current_profile]
        return "-"

    def handle_button(self, label, double):
        self.last_interaction = time.monotonic()

        if self.viewing:
            self.handle_gallery(label)
            return

        # PHOTO MODE
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
            if self.mode == 'settings':
                if double:
                    self.adjust_setting()
                else:
                    self.settings_index = (self.settings_index - 1) % len(self.settings_items)
            elif double and self.control_mode == "manual":
                self.af_mode = not self.af_mode
                self.apply_settings()
                self.flash("AF" if self.af_mode else "MF")

        elif label == 'Y':
            if self.mode == 'settings':
                if double:
                    self.adjust_setting()
                else:
                    self.settings_index = (self.settings_index + 1) % len(self.settings_items)
            elif double:
                self.shutdown()

    def adjust_setting(self):
        item = self.settings_items[self.settings_index]

        if item == "Brightness":
            self.brightness += 0.1
            if self.brightness > 1.5:
                self.brightness = 0.5

        elif item == "Focus Mode":
            self.af_mode = not self.af_mode

        elif item == "Control Mode":
            self.control_mode = "manual" if self.control_mode == "auto" else "auto"

        elif item == "ISO":
            if self.control_mode == "manual":
                self.iso += 50
                if self.iso > 800:
                    self.iso = 50

        elif item == "Shutter Speed":
            if self.control_mode == "manual":
                speeds = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
                try:
                    i = speeds.index(self.shutter_speed)
                except ValueError:
                    i = 0
                self.shutter_speed = speeds[(i + 1) % len(speeds)]

        elif item == "Profile":
            self.current_profile = (self.current_profile + 1) % len(self.profile_names)
            p = self.profiles[self.profile_names[self.current_profile]]
            self.iso = p["iso"]
            self.shutter_speed = p["shutter"]
            self.brightness = p["brightness"]
            self.af_mode = p["af_mode"]

        self.apply_settings()

    def toggle_preview(self):
        self.preview_enabled = not self.preview_enabled
        self.flash("▶" if self.preview_enabled else "⏹")

    def toggle_mode(self):
        self.mode = "settings" if self.mode == "photo" else "photo"
        self.flash("⚙" if self.mode == "settings" else "📷")

    def capture_photo(self):
        name = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
        full_path = os.path.join(PHOTO_DIR, name)
        self.picam2.capture_file(full_path)
        self.flash("✓")

    def flash(self, text):
        draw.rectangle((280, 0, 319, 20), fill=(255, 255, 255))
        draw.text((285, 2), text, font=font, fill=(0, 0, 0))
        display.display()
        time.sleep(0.4)

    def start_gallery(self):
        self.gallery = sorted(glob.glob(os.path.join(PHOTO_DIR, "*.jpg")))
        if self.gallery:
            self.viewing = True
            self.current_photo_idx = len(self.gallery) - 1
            self.show_photo()

    def handle_gallery(self, label):
        if label == 'A':
            self.viewing = False
        elif label == 'X':
            self.current_photo_idx = max(0, self.current_photo_idx - 1)
            self.show_photo()
        elif label == 'Y':
            self.current_photo_idx = min(len(self.gallery) - 1, self.current_photo_idx + 1)
            self.show_photo()

    def show_photo(self):
        try:
            path = self.gallery[self.current_photo_idx]
            img = Image.open(path).rotate(180).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
            display_image.paste(img)
            draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
            draw.text((5, 2), f"{self.current_photo_idx+1}/{len(self.gallery)}", font=font, fill=(255, 255, 255))
            display.display()
        except Exception as e:
            print("Gallery error:", e)
            self.viewing = False

    def shutdown(self):
        self.flash("OFF")
        draw.rectangle((0, 0, 320, 240), fill=(0, 0, 0))
        draw.text((60, 100), "Shutting down...", font=font, fill=(255, 0, 0))
        display.display()
        os.system("sudo shutdown now")

    def stop(self):
        self.button_handler.stop()
        self.picam2.stop()
        display.set_backlight(0)


if __name__ == "__main__":
    ui = CameraUI()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ui.stop()
        print("Exited")
