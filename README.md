# Raspberry Pi Camera
A fun little portable camera built with a Raspberry Pi Zero 2 W.

> ⚠️ Setup on other Pi models may require code modifications.  
> ⚠️ The provided disk image may not work on devices other than the Pi Zero 2 W.  

---

### Recommended Setup Tips

- To avoid SSH timeouts (on headless systems), consider using `screen` or `tmux`.
- It's recommended to increase the swap memory (helps with stability on low-RAM systems):

```bash
sudo nano /etc/dphys-swapfile
```
```bash
sudo nano /etc/dphys-swapfile
```
1.Find the line that looks something like CONF_SWAPSIZE=512
2.Change the value to something larger EX. 1024 (1GB) and save with Control + O, Return, and Control + X
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

sudo apt install python3-dev python3-setuptools libjpeg-dev zlib1g-dev libfreetype6-dev \
liblcms2-dev libopenjp2-7-dev libtiff5-dev libwebp-dev tcl8.6-dev tk8.6-dev gcc
```
5.Setup Python Virtual environment
```bash
python3 -m venv ~/cam_ui_venv
source ~/cam_ui_venv/bin/activate
```
6.Install displayhatmini
```bash
pip install --upgrade pip setuptools wheel
pip install displayhatmini Pillow
pip3 install displayhatmini
```
7.Get the development library from github
```bash
git clone https://github.com/pimoroni/displayhatmini-python
cd displayhatmini-python
sudo ./install.sh
```
8. Optional - Test the HAT
```bash
cd Pimoroni/displayhatmini/examples
python pong.py
```









