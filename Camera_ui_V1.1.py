#!/usr/bin/env python3
import os
import time
import glob
import threading
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from picamera2 import Picamera2
from displayhatmini import DisplayHATMini

# Constants
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240
PHOTO_DIR = os.path.expanduser("~/Desktop/Camera")
os.makedirs(PHOTO_DIR, exist_ok=True)
BACKLIGHT_FULL = 1.0
BACKLIGHT_DIM = 0.25
IDLE_TIMEOUT = 70
DOUBLE_PRESS_WINDOW = 0.4

BUTTONS = {
    'A': DisplayHATMini.BUTTON_A,
    'B': DisplayHATMini.BUTTON_B,
    'X': DisplayHATMini.BUTTON_X,
    'Y': DisplayHATMini.BUTTON_Y
}

display_img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT))
draw = ImageDraw.Draw(display_img)
display = DisplayHATMini(display_img)
display.set_backlight(BACKLIGHT_FULL)

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
            for label, pin in BUTTONS.items():
                pressed = display.read_button(pin)
                if pressed and not self.state[label]:
                    now = time.monotonic()
                    if label in self.last_press and (now - self.last_press[label]) < DOUBLE_PRESS_WINDOW:
                        self.callback(label, double=True)
                        self.last_press[label] = 0
                    else:
                        self.last_press[label] = now
                    self.state[label] = True
                elif not pressed and self.state[label]:
                    if self.last_press.get(label, 0):
                        if time.monotonic() - self.last_press[label] >= DOUBLE_PRESS_WINDOW:
                            self.callback(label, double=False)
                    self.state[label] = False
            time.sleep(0.05)

    def stop(self):
        self.running = False


class CameraUI:
    def __init__(self):
        self.mode = "photo"
        self.preview_enabled = True
        self.viewing = False
        self.last_interaction = time.monotonic()
        self.current_photo_idx = 0

        self.brightness = 1.0
        self.iso = 100
        self.shutter_speed = 10000
        self.af_mode = True
        self.control_mode = "auto"
        self.capture_format = "default"
        self.help_overlay = False
        self.settings_index = 0
        self.settings_items = [
            "Brightness", "Focus Mode", "Control Mode", "ISO",
            "Shutter Speed", "Profile", "Export Format", "Help Overlay"
        ]

        self.profiles = {
            "Auto": {"control_mode": "auto"},
            "Daylight": {"control_mode": "manual", "iso": 100, "shutter": 10000, "brightness": 1.0, "af_mode": True},
            "Low Light": {"control_mode": "manual", "iso": 400, "shutter": 250000, "brightness": 1.3, "af_mode": False},
            "Indoors": {"control_mode": "manual", "iso": 200, "shutter": 50000, "brightness": 1.1, "af_mode": True},
        }
        self.profile_names = list(self.profiles.keys())
        self.current_profile = 0

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 480)})
        self.picam2.configure(config)
        self.apply_settings()
        self.picam2.start()

        self.button_handler = ButtonHandler(self.handle_button)
        threading.Thread(target=self.preview_loop, daemon=True).start()

    def apply_settings(self):
        controls = {
            "AeEnable": self.control_mode == "auto",
            "AfMode": 2 if self.af_mode else 0,
        }
        if self.control_mode == "manual":
            controls.update({
                "AnalogueGain": self.iso / 100.0,
                "ExposureTime": self.shutter_speed
            })
        self.picam2.set_controls(controls)

    def preview_loop(self):
        while True:
            idle = time.monotonic() - self.last_interaction > IDLE_TIMEOUT
            display.set_backlight(BACKLIGHT_DIM if idle else BACKLIGHT_FULL)

            if self.preview_enabled and not self.viewing:
                try:
                    frame = self.picam2.capture_array()
                    image = Image.fromarray(frame).rotate(180)
                    image = ImageEnhance.Brightness(image).enhance(self.brightness)
                    image = image.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    display_img.paste(image)

                    # Top Status Bar
                    draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
                    draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))
                    draw.text((265, 2), "AF" if self.af_mode else "MF", font=font, fill=(255, 255, 0))

                    # Settings Feedback Bar
                    if self.mode == "settings":
                        item = self.settings_items[self.settings_index]
                        draw.rectangle((0, 200, 320, 240), fill=(0, 0, 0))
                        draw.text((5, 210), f"{item}: {self.get_setting_value(item)}", font=font, fill=(255, 255, 255))

                    # Help Overlay
                    if self.help_overlay:
                        draw.rectangle((0, 165, 320, 200), fill=(0, 0, 0))
                        draw.text((5, 168), "A: Photo  B: Gallery  X: ◀  Y: ▶", font=font, fill=(150, 255, 150))
                        draw.text((5, 185), "Double: Settings, Adjust, AF, Shutdown", font=font, fill=(150, 240, 255))

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
            return f"{self.shutter_speed // 1000} ms" if self.control_mode == "manual" else "AUTO"
        elif item == "Profile":
            return self.profile_names[self.current_profile]
        elif item == "Export Format":
            return self.capture_format.upper()
        elif item == "Help Overlay":
            return "ON" if self.help_overlay else "OFF"
        return "-"

    def handle_button(self, label, double):
        self.last_interaction = time.monotonic()

        if self.viewing:
            if label == 'X':
                self.current_photo_idx = max(0, self.current_photo_idx - 1)
            elif label == 'Y':
                self.current_photo_idx = min(len(self.gallery) - 1, self.current_photo_idx + 1)
            elif label == 'A':
                self.viewing = False
            if self.viewing:
                self.display_gallery_photo()
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
            if self.mode == "settings":
                if double:
                    self.change_setting(increment=False)
                else:
                    self.settings_index = (self.settings_index - 1) % len(self.settings_items)
            elif double:
                self.af_mode = not self.af_mode
                self.apply_settings()
                self.flash("AF" if self.af_mode else "MF")
        elif label == 'Y':
            if self.mode == "settings":
                if double:
                    self.change_setting(increment=True)
                else:
                    self.settings_index = (self.settings_index + 1) % len(self.settings_items)
            elif double:
                self.shutdown()

    def change_setting(self, increment=True):
        delta = 1 if increment else -1
        item = self.settings_items[self.settings_index]
        if item == "Brightness":
            self.brightness += 0.1 * delta
            if self.brightness < 0.5: self.brightness = 1.5
            elif self.brightness > 1.5: self.brightness = 0.5
        elif item == "Focus Mode":
            self.af_mode = not self.af_mode
        elif item == "Control Mode":
            self.control_mode = "manual" if self.control_mode == "auto" else "auto"
        elif item == "ISO" and self.control_mode == "manual":
            self.iso += 50 * delta
            if self.iso < 50: self.iso = 800
            elif self.iso > 800: self.iso = 50
        elif item == "Shutter Speed" and self.control_mode == "manual":
            options = [1000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
            i = options.index(self.shutter_speed) if self.shutter_speed in options else 0
            self.shutter_speed = options[(i + delta) % len(options)]
        elif item == "Profile":
            self.current_profile = (self.current_profile + delta) % len(self.profile_names)
            profile = self.profiles[self.profile_names[self.current_profile]]
            self.control_mode = profile.get("control_mode", "auto")
            self.brightness = profile.get("brightness", 1.0)
            self.iso = profile.get("iso", 100)
            self.shutter_speed = profile.get("shutter", 10000)
            self.af_mode = profile.get("af_mode", True)
        elif item == "Export Format":
            formats = ["default", "jpeg", "raw"]
            i = formats.index(self.capture_format)
            self.capture_format = formats[(i + delta) % len(formats)]
        elif item == "Help Overlay":
            self.help_overlay = not self.help_overlay
        self.apply_settings()

    def toggle_mode(self):
        if self.mode == "settings":
            self.mode = "photo"
            self.preview_enabled = True  # ✅ FIXED: Black screen bug
        else:
            self.mode = "settings"
        self.flash("⚙" if self.mode == "settings" else "📷")

    def flash(self, icon):
        draw.rectangle((280, 0, 319, 20), fill=(255, 255, 255))
        draw.text((285, 2), icon, font=font, fill=(0, 0, 0))
        display.display()
        time.sleep(0.3)

    def toggle_preview(self):
        self.preview_enabled = not self.preview_enabled
        self.flash("▶" if self.preview_enabled else "■")

    def capture_photo(self):
        filename = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
        path = os.path.join(PHOTO_DIR, filename)
        if self.capture_format == "raw":
            self.picam2.capture_file(path, format="jpeg", capture_raw=True)
        elif self.capture_format == "jpeg":
            self.picam2.capture_file(path, format="jpeg")
        else:
            self.picam2.capture_file(path)
        self.flash("✓")

    def start_gallery(self):
        self.gallery = sorted(glob.glob(os.path.join(PHOTO_DIR, '*.jpg')))
        if self.gallery:
            self.viewing = True
            self.current_photo_idx = len(self.gallery) - 1
            self.display_gallery_photo()

    def display_gallery_photo(self):
        try:
            img = Image.open(self.gallery[self.current_photo_idx]).rotate(180).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
            display_img.paste(img)
            draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
            draw.text((5, 2), f"{self.current_photo_idx + 1}/{len(self.gallery)}", font=font, fill=(255, 255, 255))
            display.display()
        except Exception as e:
            print("Gallery error:", e)
            self.viewing = False

    def shutdown(self):
        self.flash("OFF")
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
    ui = CameraUI()
    print("Camera UI running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ui.stop()
