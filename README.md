# Acer Nitro Fan Management (`nitro-fan`)

A dedicated fan speed and cooling management suite for **Acer Nitro V 15** (`ANV15-41`, `ANV15-51`) and modern Acer Nitro laptops running Linux.

Unlike legacy utilities that poke raw bytes into physical Embedded Controller (EC) memory, this project interfaces with the official **Acer ACPI-WMI** methods (`AcerGamingFunction`) used by official Windows NitroSense.

---

## Features

- **Direct WMI Fan Control**: Max Turbo (100%), Automatic (BIOS Managed), and Custom fan speeds.
- **Pure Fan Focus**: Zero battery limiter or keyboard backlight clutter—100% cooling & thermal performance.
- **DKMS Kernel Driver**: Pre-configured `linuwu-sense` module automatically rebuilt across Linux kernel updates.
- **Passwordless Control**: Udev rules grant instant write access without entering your `sudo` password.
- **Rich CLI**: Status inspection, real-time live terminal dashboard (`watch`), and quick fan presets.
- **Modern PyQt6 GUI**: Sleek carbon dark theme, live RPM meters, temperature monitoring, and interactive sliders.
- **Desktop Entry**: Launches directly from your desktop application launcher.

---

## Quick Start (CLI)

```bash
# Check current fan speeds, active mode, and CPU temperature
nitro-fan status

# Force 100% Full Blast Turbo cooling
nitro-fan max

# Return to automatic BIOS fan curve
nitro-fan auto

# Set custom fan speeds (CPU % and GPU %)
nitro-fan set 75 65

# Launch real-time live updating terminal dashboard
nitro-fan watch

# Launch the Graphical User Interface
nitro-fan gui
```

> **Note:** The `nitrosense` command is also aliased to `nitro-fan`.

---

## Graphical User Interface (GUI)

Launch the interface via terminal or your desktop app menu:

```bash
nitro-fan gui
```

Features:
- Real-time CPU & GPU Fan RPM readouts
- Package and thermal sensor temperatures with threshold color-coding
- One-click presets: **Auto**, **Quiet (40%)**, **Balanced (65%)**, **Heavy (85%)**, and **Max Turbo (100%)**
- Dual sliders for independent CPU and GPU fan percentage tuning

---

## Project Structure

```text
Linux-NitroSense/
├── assets/
│   └── nitro-fan.svg        # Scalable application icon
├── bin/
│   └── nitro-fan            # Unified CLI & GUI launcher
├── cli/
│   └── nitro_fan.py         # Command-line telemetry and fan control engine
├── driver/
│   └── linuwu-sense/        # Submodule for ACPI-WMI kernel driver (DKMS)
├── gui/
│   └── nitro_gui.py         # Modern PyQt6 graphical user interface
├── install.sh               # Complete setup script (DKMS, udev rules, desktop launcher)
├── nitro-fan.desktop        # Application menu shortcut
└── README.md
```

---

## Installation & Reinstallation

To reinstall or refresh all components:

```bash
sudo ./install.sh
```

The installer automatically:
1. Registers the kernel module with DKMS.
2. Creates udev permissions for passwordless control.
3. Links the executable to `/usr/local/bin/nitro-fan`.
4. Installs the desktop application launcher.
