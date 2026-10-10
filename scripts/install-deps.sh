#!/bin/sh
set -eu
sudo apt-get update
sudo apt-get install -y build-essential cmake libfltk1.3-dev libgnutls28-dev \
    libjpeg-dev libpixman-1-dev libpam0g-dev zlib1g-dev libx11-dev libxext-dev \
    libxrandr-dev libxi-dev libxfixes-dev libxcursor-dev libxinerama-dev \
    libxrender-dev libxtst-dev dpkg-dev python3-gi python3-pil gir1.2-gtk-3.0 \
    gir1.2-secret-1 gnome-keyring desktop-file-utils libglib2.0-bin fonts-noto-cjk
