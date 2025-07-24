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
IDLE_TIMEOUT = 70  # seconds
DELETE_HOLD_TIME = 2.0

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
        self.pressed_time = {}
        self.running = True
        threading.Thread(target=self.poll, daemon=True).start()

    def poll(self):
        while self.running:
            now = time.monotonic()
            for label, pin in BUTTONS.items():
                pressed = display.read_button(pin)
                prev = self.state[label]
                self.state[label] = pressed

                if pressed and not prev:
                    self.pressed_time[label] = now
                    self.callback(label, double=False, pressed=True)

                elif not pressed and prev:
                    duration = now - self.pressed_time.get(label, now)
                    self.callback(label, double=False, pressed=False)

            time.sleep(0.05)

    def stop(self):
        self.running = False


class CameraUI:
    def __init__(self):
        self.mode = "photo"
        self.preview_enabled = True
        self.viewing = False
        self.awaiting_confirm = False
        self.delete_confirm_stage = False
        self.last_interaction = time.monotonic()
        self.combo_timer = None
        self.gallery = []
        self.current_photo_idx = 0

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(main={"size": (640, 480)})
        self.picam2.configure(config)
        self.picam2.set_controls({"AfMode": 2})  # Continuous AF by default
        self.picam2.start()

        self.button_handler = ButtonHandler(self.handle_button)
        threading.Thread(target=self.preview_loop, daemon=True).start()

    def preview_loop(self):
        while True:
            now = time.monotonic()
            idle = now - self.last_interaction > IDLE_TIMEOUT
            display.set_backlight(BACKLIGHT_DIM if idle else BACKLIGHT_FULL)

            if self.preview_enabled and not self.viewing:
                try:
                    frame = self.picam2.capture_array()
                    image = Image.fromarray(frame).rotate(180)
                    image = image.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))
                    display_img.paste(image)

                    # Top Status Bar
                    draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
                    draw.text((5, 2), f"Mode: {self.mode}", font=font, fill=(255, 255, 255))

                    count = len(glob.glob(os.path.join(PHOTO_DIR, "*.jpg")))
                    draw.text((240, 2), f"{count} photos", font=font, fill=(100, 255, 100))

                    display.display()
                except:
                    pass
            time.sleep(0.1)

    def handle_button(self, label, double, pressed):
        self.last_interaction = time.monotonic()

        # Handle delete confirm
        if self.delete_confirm_stage:
            if not pressed:
                if label == 'A':
                    self.confirm_delete()
                elif label == 'B':
                    self.cancel_delete()
            return

        # Gallery view mode
        if self.viewing:
            if self.check_delete_combo():
                return

            if not pressed:
                if label == 'A':
                    self.viewing = False
                elif label == 'X':
                    self.current_photo_idx = max(0, self.current_photo_idx - 1)
                    self.display_gallery_photo()
                elif label == 'Y':
                    self.current_photo_idx = min(len(self.gallery) - 1, self.current_photo_idx + 1)
                    self.display_gallery_photo()
            return

        # Normal buttons in photo mode
        if not pressed:
            if label == 'A':
                self.capture_photo()
            elif label == 'B':
                self.view_gallery()

    def is_held(self, other):
        return display.read_button(BUTTONS[other])

    def check_delete_combo(self):
        if self.is_held('X') and self.is_held('Y'):
            if not self.combo_timer:
                self.combo_timer = time.monotonic()
            elif time.monotonic() - self.combo_timer > DELETE_HOLD_TIME:
                self.prompt_delete_confirmation()
                self.combo_timer = None
            return True
        else:
            self.combo_timer = None
            return False

    def prompt_delete_confirmation(self):
        self.delete_confirm_stage = True
        draw.rectangle((0, 0, 320, 240), fill=(0, 0, 0))
        draw.text((60, 100), "Delete this photo?", font=font, fill=(255, 0, 0))
        draw.text((60, 130), "A = Yes   B = Cancel", font=font, fill=(255, 255, 255))
        display.display()

    def confirm_delete(self):
        self.delete_confirm_stage = False
        self.delete_photo()

    def cancel_delete(self):
        self.delete_confirm_stage = False
        self.display_gallery_photo()

    def delete_photo(self):
        try:
            path = self.gallery[self.current_photo_idx]
            os.remove(path)
            self.gallery.pop(self.current_photo_idx)
            self.current_photo_idx = max(0, self.current_photo_idx - 1)
            self.flash_ui("DEL")
            if not self.gallery:
                self.viewing = False
            else:
                self.display_gallery_photo()
        except Exception as e:
            print("Failed to delete:", e)
            self.viewing = False

    def view_gallery(self):
        self.gallery = sorted(glob.glob(os.path.join(PHOTO_DIR, "*.jpg")))
        if self.gallery:
            self.viewing = True
            self.current_photo_idx = len(self.gallery) - 1
            self.display_gallery_photo()

    def display_gallery_photo(self):
        try:
            img_path = self.gallery[self.current_photo_idx]
            img = Image.open(img_path).rotate(180).resize((320, 240))
            display_img.paste(img)
            draw.rectangle((0, 0, 320, 20), fill=(0, 0, 0))
            draw.text((5, 2), f"{self.current_photo_idx+1}/{len(self.gallery)}", font=font, fill=(255, 255, 255))
            display.display()
        except:
            self.viewing = False

    def capture_photo(self):
        filename = time.strftime("IMG_%Y%m%d_%H%M%S.jpg")
        path = os.path.join(PHOTO_DIR, filename)
        self.picam2.capture_file(path)
        self.flash_ui("✓")

    def toggle_preview(self):
        self.preview_enabled = not self.preview_enabled
        self.flash_ui("▶" if self.preview_enabled else "■")

    def flash_ui(self, icon):
        draw.rectangle((280, 0, 319, 20), fill=(255, 255, 255))
        draw.text((285, 2), icon, font=font, fill=(0, 0, 0))
        display.display()
        time.sleep(0.3)

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
