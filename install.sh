#!/usr/bin/env bash
# Hardware Fan Management System Installer
# Sets up driver, udev rules for passwordless control, CLI, and GUI shortcuts

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}        Hardware Fan Management Installer           ${NC}"
echo -e "${BLUE}====================================================${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}[!] Escalating to root with sudo/pkexec...${NC}"
    exec sudo "$0" "$@"
fi

echo -e "${BLUE}[1/5] Setting up DKMS kernel driver...${NC}"
DKMS_SRC="/usr/src/linuwu-sense-1.0"
rm -rf "$DKMS_SRC"
cp -r "$PROJECT_DIR/driver/linuwu-sense" "$DKMS_SRC"
dkms remove linuwu-sense/1.0 --all 2>/dev/null || true
dkms add linuwu-sense/1.0
dkms build linuwu-sense/1.0
dkms install linuwu-sense/1.0

# Set up module auto-loading on boot
echo "linuwu_sense" > /etc/modules-load.d/linuwu_sense.conf
echo "blacklist acer_wmi" > /etc/modprobe.d/blacklist-acer-wmi.conf

echo -e "${BLUE}[2/5] Configuring passwordless fan control permissions (udev & tmpfiles)...${NC}"
cat << "EOF" > /etc/udev/rules.d/99-nitro-fans.rules
ACTION=="add|change", SUBSYSTEM=="platform", ATTR{nitro_sense/fan_speed}!="", RUN+="/bin/chmod 0666 /sys/devices/platform/acer-wmi/nitro_sense/fan_speed"
EOF
udevadm control --reload-rules && udevadm trigger 2>/dev/null || true

cat << "EOF" > /etc/tmpfiles.d/nitro-fans.conf
z /sys/devices/platform/acer-wmi/nitro_sense/fan_speed 0666 root root -
EOF

# Grant immediate write permission if module is already active
if [ -f "/sys/devices/platform/acer-wmi/nitro_sense/fan_speed" ]; then
    chmod 0666 /sys/devices/platform/acer-wmi/nitro_sense/fan_speed
fi

echo -e "${BLUE}[3/5] Installing CLI binary in /usr/local/bin...${NC}"
chmod +x "$PROJECT_DIR/bin/nitrofan"
ln -sf "$PROJECT_DIR/bin/nitrofan" /usr/local/bin/nitrofan
rm -f /usr/local/bin/nitro-fan /usr/local/bin/nitrosense 2>/dev/null || true

echo -e "${BLUE}[4/5] Installing desktop application launcher...${NC}"
DESKTOP_FILE="$PROJECT_DIR/nitrofan.desktop"
cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=Fan Control Center
Comment=Hardware fan speed and cooling management for Linux
Exec=$PROJECT_DIR/bin/nitrofan gui
Icon=$PROJECT_DIR/assets/nitrofan.svg
Terminal=false
Type=Application
Categories=System;Settings;HardwareSettings;
Keywords=fan;cooling;thermal;fan-control;
EOF
cp "$DESKTOP_FILE" /usr/share/applications/ 2>/dev/null || true
rm -f /usr/share/applications/nitro-fan.desktop 2>/dev/null || true
update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo -e "${BLUE}[5/5] Ensuring kernel driver is active...${NC}"
modprobe sparse_keymap 2>/dev/null || true
modprobe -r acer_wmi 2>/dev/null || true
modprobe linuwu_sense 2>/dev/null || true

echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}   [✓] Fan Management Suite Successfully Installed! ${NC}"
echo -e "${GREEN}====================================================${NC}"
echo ""
echo "Quick Commands:"
echo "  nitrofan status       # View real-time fan RPMs, mode, and temps"
echo "  nitrofan max          # Force 100% Turbo cooling"
echo "  nitrofan auto         # Restore automatic BIOS fan curves"
echo "  nitrofan set 75 75    # Custom fan percentage"
echo "  nitrofan watch        # Live terminal monitoring dashboard"
echo "  nitrofan gui          # Launch graphical user interface"
echo ""
