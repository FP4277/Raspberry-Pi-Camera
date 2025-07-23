#!/usr/bin/env python3
import os
import time
import threading
import glob
import json
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from picamera2 import Picamera2
from displayhatmini import DisplayHATMini

# Constants
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
PHOTO_DIR = os.path.expanduser("~/Desktop/Camera")
SETTINGS_FILE = os.path.expanduser("~/CameraSettings.json")
os.makedirs(PHOTO_DIR, exist_ok=True)
BACKLIGHT_BRIGHT = 1.0
BACKLIGHT_DIM = 0.25
IDLE_TIMEOUT = 70
DOUBLE_PRESS_WINDOW = 0.45

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
        self.gallery = []
        self.settings_index = 0
        self.iso = 100
        self.brightness = 1.0
        self.af_mode = True
        self.auto_mode = True
        self.shutter_us = 0

        self.settings_items = ['ISO', 'Brightness', 'Focus Mode', 'Auto Mode', 'Shutter']

        self.profiles = {
            "Default": {"iso": 100, "shutter_us": 0, "brightness": 1.0},
            "Daylight": {"iso": 100, "shutter_us": 1000, "brightness": 1.0},
            "Indoors": {"iso": 200, "shutter_us": 20000, "brightness": 1.1},
            "Night": {"iso": 600, "shutter_us": 100000, "brightness": 1.3},
        }
        self.profile_names = list(self.profiles.keys())
        self.current_profile_index = 0

        self.load_settings()

        self.picam2 = Picamera2()
        preview_config = self.picam2.create_preview_configuration(main={"size": (640, 480)})
        self.picam2.configure(preview_config)
        self.apply_settings()
        self.picam2.start()

        self.button_handler = ButtonHandler(self.handle_button)
        self.preview_thread = threading.Thread(target=self.preview_loop, daemon=True)
        self.preview_thread.start()

    def save_settings(self):
        data = {
            "iso": self.iso,
            "brightness": self.brightness,
            "af_mode": self.af_mode,
            "auto_mode": self.auto_mode,
            "shutter_us": self.shutter_us
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print("Couldn't save settings:", e)

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                self.iso = data.get("iso", 100)
                self.brightness = data.get("brightness", 1.0)
                self.af_mode = data.get("af_mode", True)
                self.auto_mode = data.get("auto_mode", True)
                self.shutter_us = data.get("shutter_us", 0)
        except:
            self.shutter_us = 0

    def apply_settings(self):
        controls = {
            "AfMode": 2 if self.af_mode else 0,
            "AwbEnable": True
        }
        if self.auto_mode:
            controls["AeEnable"] = True
            controls["ExposureTime"] = 0
            controls["AnalogueGain"] = 0
        else:
            controls["AeEnable"] = False
            controls["AnalogueGain"] = self.iso / 100.0
            controls["ExposureTime"] = self.shutter_us if self.shutter_us else 0
        self.picam2.set_controls(controls)

    def preview_loop(self):
        while True:
            idle = (time.monotonic() - self.last_interaction > IDLE_TIMEOUT)
            display.set_backlight(BACKLIGHT_DIM if idle else BACKLIGHT_BRIGHT)
            if self.preview_enabled and not self.viewing:
                try:
                    frame = Image.fromarray(self.picam2.capture_array()).rotate(180)
                    frame = ImageEnhance.Brightness(frame).enhance(self.brightness)
                    frame = frame.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    display_image.paste(frame)
                    draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
                    draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))
                    draw.text((260, 2), "AF" if self.af_mode else "MF", font=font, fill=(255, 255, 255))
                    if self.mode == 'settings':
                        item = self.settings_items[self.settings_index]
                        val = self.get_value(item)
                        draw.rectangle((0, 200, 320, 240), fill=(0, 0, 0))
                        draw.text((5, 210), f"{item}: {val}", font=font, fill=(255, 255, 0))
                    display.display()
                except:
                    pass
            time.sleep(0.1)

    def get_value(self, item):
        if item == 'ISO':
            return "Auto" if self.auto_mode else str(self.iso)
        elif item == 'Brightness':
            return f"{int(self.brightness * 100)}%"
        elif item == 'Focus Mode':
            return "AF" if self.af_mode else "MF"
        elif item == 'Auto Mode':
            return "ON" if self.auto_mode else "OFF"
        elif item == 'Shutter':
            if self.auto_mode or not self.shutter_us:
                return "Auto"
            else:
                return f"{int(self.shutter_us / 1000)}ms"
        return "-"

    def adjust_setting(self):
        item = self.settings_items[self.settings_index]
        if item == 'ISO':
            if not self.auto_mode:
                self.iso += 50
                if self.iso > 800:
                    self.iso = 50
        elif item == 'Brightness':
            self.brightness += 0.1
            if self.brightness > 1.5:
                self.brightness = 0.5
        elif item == 'Focus Mode':
            self.af_mode = not self.af_mode
        elif item == 'Auto Mode':
            self.auto_mode = not self.auto_mode
            if self.auto_mode:
                self.iso = 100
                self.shutter_us = 0
        elif item == 'Shutter':
            if not self.auto_mode:
                self.shutter_us += 10000
                if self.shutter_us > 250000:
                    self.shutter_us = 0
        self.apply_settings()
        self.save_settings()

    def capture_photo(self):
        try:
            filename = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
            path = os.path.join(PHOTO_DIR, filename)
            self.picam2.capture_file(path)
            self.flash_icon("✓")
        except:
            self.flash_icon("X")

    def toggle_af(self):
        self.af_mode = not self.af_mode
        self.apply_settings()
        self.save_settings()
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
        time.sleep(0.3)

    def start_gallery(self):
        self.gallery = sorted(glob.glob(os.path.join(PHOTO_DIR, '*.jpg')))
        if self.gallery:
            self.current_photo_index = len(self.gallery) - 1
            self.viewing = True
            self.show_current_photo()

    def handle_gallery_view(self, label):
        if label == 'A':
            self.viewing = False
        elif label == 'X':
            self.current_photo_index = max(0, self.current_photo_index - 1)
            self.show_current_photo()
        elif label == 'Y':
            self.current_photo_index = min(len(self.gallery) - 1, self.current_photo_index + 1)
            self.show_current_photo()

    def show_current_photo(self):
        try:
            img_path = self.gallery[self.current_photo_index]
            img = Image.open(img_path).rotate(180).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
            display_image.paste(img)
            draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
            draw.text((5, 2), f"{self.current_photo_index+1}/{len(self.gallery)}", font=font, fill=(255, 255, 255))
            display.display()
        except:
            self.flash_icon("?")
            self.viewing = False

    def load_profile(self, index):
        prof = self.profiles[self.profile_names[index]]
        self.iso = prof["iso"]
        self.shutter_us = prof["shutter_us"]
        self.brightness = prof["brightness"]
        self.auto_mode = False
        self.apply_settings()
        self.save_settings()
        self.flash_icon(self.profile_names[index][0])

    def handle_button(self, label, double):
        now = time.monotonic()
        if now - self.last_interaction > IDLE_TIMEOUT and not double and label in ['X', 'Y']:
            self.last_interaction = now
            return
        self.last_interaction = now

        if self.viewing:
            self.handle_gallery_view(label)
            return

        if label == 'A':
            if double:
                self.toggle_preview()
            else:
                self.capture_photo()
        elif label == 'B':
            if double:
                self.current_profile_index = (self.current_profile_index + 1) % len(self.profile_names)
                self.load_profile(self.current_profile_index)
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

    def shutdown(self):
        self.flash_icon("OFF")
        draw.rectangle((0, 0, 320, 240), fill=(0, 0, 0))
        draw.text((60, 110), "Shutting down...", font=font, fill=(255, 0, 0))
        display.display()
        time.sleep(1)
        os.system("sudo shutdown now")

    def stop(self):
        self.picam2.stop()
        self.button_handler.stop()
        display.set_backlight(0)

if __name__ == "__main__":
    print("Camera running. Press Ctrl+C to exit.")
    ui = CameraUI()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
        ui.stop()
