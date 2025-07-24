# Raspberry Pi Camera
A fun little portable camera built with a Raspberry Pi Zero 2 W.
## ✅ Features
- Auto / Manual exposure control
- Manual shutter speed and ISO
- Autofocus toggle
- Live image preview
- Photo capture (JPEG / RAW)
- User-selectable profiles (Low Light, Indoors, Daylight, Auto)
- Image gallery viewer
- Help overlay
- Metering mode: average / center / spot
- Screen dimming after idle
- Button-powered settings navigation
- Designed for Raspberry Pi Zero 2 W + Pi Camera 3
> ⚠️ Setup on other Pi models may require code modifications.  
> ⚠️ The provided disk image may not work on devices other than the Pi Zero 2 W.  

---

### Recommended Setup Tips

- To avoid SSH timeouts (on headless systems), consider using `screen` or `tmux`.
- It's recommended to increase the swap memory (helps with stability on low-RAM systems):

```bash
sudo nano /etc/dphys-swapfile
```
1.Find the line  CONF_SWAPSIZE=512
2.Change the value to something larger Ex. 1024 (1GB) and save with Control + O, Return, and Control + X
3.Restart the swap service
```bash
sudo systemctl restart dphys-swapfile
free -h
```
4. Prepare the system:
```bash
sudo raspi-config nonint do_spi 0

sudo apt update && sudo apt upgrade -y

sudo apt install python3 python3-venv python3-pip -y

sudo apt install libopenblas0

sudo apt install git -y

sudo apt install python3-dev python3-setuptools libjpeg-dev zlib1g-dev libfreetype6-dev \
liblcms2-dev libopenjp2-7-dev libtiff5-dev libwebp-dev tcl8.6-dev tk8.6-dev gcc

sudo apt install libcamera-apps python3-picamera2
```
5.Setup Python Virtual environment
```bash
python3 -m venv --system-site-packages cam_ui_venv
source ~/cam_ui_venv/bin/activate
```
6.Install displayhatmini
```bash
pip install --upgrade pip setuptools wheel
pip install displayhatmini pillow pygame
pip3 install displayhatmini
pip install "numpy<2.0.0"
```
7.Get the displayhat development library from github
```bash
git clone https://github.com/pimoroni/displayhatmini-python
cd displayhatmini-python
sudo ./install.sh
```
8. Optional - Test the HAT and camera
```bash
cd Pimoroni/displayhatmini/examples
python pong.py
```
9. Setup the UI script as a systemd service
```bash
mkdir Camera_Project
cd Camera_Project
```
10. Save the UI script to the Camera_Project directory
```bash
nano camera_ui.py
chmod +x camera_ui.py
./camera_ui.py
```
11. Make the systemd service
```bash
sudo nano /etc/systemd/system/camera-ui.service
```
12. Paste
```bash
[Unit]
Description=Camera UI - William Pi
After=network.target

[Service]
User=william
Group=william
WorkingDirectory=/home/william/Camera_Project
ExecStart=/home/william/cam_ui_venv/bin/python /home/william/Camera_Project/camera_ui.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
13. Start the service
```bash
sudo systemctl daemon-reload                 # Reload definitions
sudo systemctl enable camera-ui.service     # Enable on boot
sudo systemctl start camera-ui.service      # Start now
```
14. Check the status - look for: active (running)
```bash
sudo systemctl status camera-ui.service
```
-If you want to update the camera script follow the steps below
1. Stop the camera_UI systemd service
```bash
sudo systemctl stop camera-ui.service
```
2. Replace or edit camera_ui.py in the Camera_Project directory
3. Start the systemd service
```bash
sudo systemctl start camera-ui.service
```
or 
```bash
sudo systemctl restart camera-ui.service
```
to start everything again

















