#!/usr/bin/env python3
"""
Nitro-Fan GUI
-------------
Modern, dark-themed PyQt6 interface for Acer Nitro fan control.
100% focused on fan speeds, thermal monitoring, and cooling performance.
"""

import os
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Add parent directory to path to import CLI telemetry helpers
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cli.nitro_fan import is_driver_loaded, read_telemetry, set_fan_speed

class MetricCard(QFrame):
    """Custom styled metric display card."""
    def __init__(self, title, unit="RPM", color="#FF3333"):
        super().__init__()
        self.unit = unit
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: #1A1A1A;
                border: 1px solid #2D2D2D;
                border-radius: 12px;
                padding: 12px;
            }}
            MetricCard:hover {{
                border: 1px solid {color};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #888888; font-size: 13px; font-weight: bold; text-transform: uppercase;")
        
        self.value_label = QLabel(f"0 {unit}")
        self.value_label.setStyleSheet(f"color: #FFFFFF; font-size: 26px; font-weight: bold;")
        
        self.sub_label = QLabel("Active")
        self.sub_label.setStyleSheet("color: #555555; font-size: 11px;")
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)

    def set_value(self, val, subtext=None, color=None):
        self.value_label.setText(f"{val} {self.unit}")
        if color:
            self.value_label.setStyleSheet(f"color: {color}; font-size: 26px; font-weight: bold;")
        if subtext:
            self.sub_label.setText(subtext)

class NitroWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acer Nitro Fan Management")
        self.setFixedSize(560, 680)
        
        self._setup_theme()
        self._init_ui()
        
        # Live telemetry timer (1000ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_telemetry)
        self.timer.start(1000)
        self.update_telemetry()

    def _setup_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(18, 18, 18))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, QColor(32, 32, 32))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(229, 9, 20))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header Banner
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("NITRO FAN CONTROL")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #FF2A2A; letter-spacing: 1px;")
        
        subtitle = QLabel("Acer Nitro V & Modern Nitro Platform")
        subtitle.setStyleSheet("color: #777777; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        
        header.addStretch()
        
        self.status_badge = QLabel(" WMI CONNECTED ")
        self.status_badge.setStyleSheet("""
            background-color: #103318;
            color: #00FF66;
            border: 1px solid #00AA44;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 8px;
        """)
        header.addWidget(self.status_badge)
        main_layout.addLayout(header)

        # Telemetry Grid (RPM and Temps)
        grid = QGridLayout()
        grid.setSpacing(12)
        
        self.card_cpu_fan = MetricCard("CPU FAN SPEED", "RPM", "#FF4444")
        self.card_gpu_fan = MetricCard("GPU FAN SPEED", "RPM", "#FF4444")
        self.card_cpu_temp = MetricCard("CPU TEMP", "°C", "#00E5FF")
        self.card_gpu_temp = MetricCard("GPU TEMP", "°C", "#00E5FF")
        
        grid.addWidget(self.card_cpu_fan, 0, 0)
        grid.addWidget(self.card_gpu_fan, 0, 1)
        grid.addWidget(self.card_cpu_temp, 1, 0)
        grid.addWidget(self.card_gpu_temp, 1, 1)
        main_layout.addLayout(grid)

        # Fan Mode Selection (Auto vs Turbo vs Custom)
        mode_box = QGroupBox("FAN PROFILE PRESETS")
        mode_box.setStyleSheet("""
            QGroupBox {
                color: #AAAAAA;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #2B2B2B;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.setSpacing(10)

        self.btn_auto = QPushButton("AUTO (NORMAL)")
        self.btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto.setStyleSheet("""
            QPushButton {
                background-color: #1E281E;
                color: #44FF44;
                border: 1px solid #336633;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #274027; border: 1px solid #55FF55; }
        """)
        self.btn_auto.clicked.connect(self._set_auto)

        self.btn_max = QPushButton("MAX TURBO (100%)")
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_max.setStyleSheet("""
            QPushButton {
                background-color: #331414;
                color: #FF3333;
                border: 1px solid #772222;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4A1A1A; border: 1px solid #FF5555; }
        """)
        self.btn_max.clicked.connect(self._set_max)

        mode_layout.addWidget(self.btn_auto)
        mode_layout.addWidget(self.btn_max)
        main_layout.addWidget(mode_box)

        # Custom Fan Sliders Group
        slider_box = QGroupBox("MANUAL FAN SPEED ADJUSTMENT")
        slider_box.setStyleSheet(mode_box.styleSheet())
        slider_layout = QVBoxLayout(slider_box)
        slider_layout.setSpacing(12)

        # CPU Fan Slider
        cpu_row = QHBoxLayout()
        cpu_label = QLabel("CPU Fan Speed:")
        cpu_label.setStyleSheet("color: #CCCCCC; font-size: 13px; font-weight: bold;")
        self.cpu_pct_label = QLabel("Auto")
        self.cpu_pct_label.setStyleSheet("color: #FF2A2A; font-size: 13px; font-weight: bold;")
        cpu_row.addWidget(cpu_label)
        cpu_row.addStretch()
        cpu_row.addWidget(self.cpu_pct_label)
        slider_layout.addLayout(cpu_row)

        self.cpu_slider = QSlider(Qt.Orientation.Horizontal)
        self.cpu_slider.setRange(0, 100)
        self.cpu_slider.setValue(0)
        self.cpu_slider.setStyleSheet(self._slider_style())
        self.cpu_slider.valueChanged.connect(self._on_slider_moved)
        slider_layout.addWidget(self.cpu_slider)

        # GPU Fan Slider
        gpu_row = QHBoxLayout()
        gpu_label = QLabel("GPU Fan Speed:")
        gpu_label.setStyleSheet("color: #CCCCCC; font-size: 13px; font-weight: bold;")
        self.gpu_pct_label = QLabel("Auto")
        self.gpu_pct_label.setStyleSheet("color: #FF2A2A; font-size: 13px; font-weight: bold;")
        gpu_row.addWidget(gpu_label)
        gpu_row.addStretch()
        gpu_row.addWidget(self.gpu_pct_label)
        slider_layout.addLayout(gpu_row)

        self.gpu_slider = QSlider(Qt.Orientation.Horizontal)
        self.gpu_slider.setRange(0, 100)
        self.gpu_slider.setValue(0)
        self.gpu_slider.setStyleSheet(self._slider_style())
        self.gpu_slider.valueChanged.connect(self._on_slider_moved)
        slider_layout.addWidget(self.gpu_slider)

        # Quick Preset Buttons
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        for pct, name in [(40, "Quiet (40%)"), (65, "Balanced (65%)"), (85, "Heavy (85%)"), (100, "Full (100%)")]:
            btn = QPushButton(name)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #242424;
                    color: #CCCCCC;
                    border: 1px solid #3A3A3A;
                    border-radius: 6px;
                    padding: 6px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #333333; color: #FFFFFF; }
            """)
            btn.clicked.connect(lambda _, p=pct: self._apply_preset(p))
            preset_row.addWidget(btn)
        slider_layout.addLayout(preset_row)

        # Apply Custom Button
        self.btn_apply = QPushButton("APPLY CUSTOM FAN SPEEDS")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #E50914;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
            QPushButton:hover { background-color: #FF1E27; }
        """)
        self.btn_apply.clicked.connect(self._apply_custom)
        slider_layout.addWidget(self.btn_apply)

        main_layout.addWidget(slider_box)
        main_layout.addStretch()

    def _slider_style(self):
        return """
            QSlider::groove:horizontal {
                height: 8px;
                background: #252525;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #880000, stop:1 #FF2A2A);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #FF2A2A;
                width: 18px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #FF2A2A;
            }
        """

    def _on_slider_moved(self):
        c_val = self.cpu_slider.value()
        g_val = self.gpu_slider.value()
        self.cpu_pct_label.setText(f"{c_val}%" if c_val > 0 else "Auto (0%)")
        self.gpu_pct_label.setText(f"{g_val}%" if g_val > 0 else "Auto (0%)")

    def _apply_preset(self, pct):
        self.cpu_slider.setValue(pct)
        self.gpu_slider.setValue(pct)
        self._apply_custom()

    def _set_auto(self):
        self.cpu_slider.setValue(0)
        self.gpu_slider.setValue(0)
        set_fan_speed(0, 0)
        self.update_telemetry()

    def _set_max(self):
        self.cpu_slider.setValue(100)
        self.gpu_slider.setValue(100)
        set_fan_speed(100, 100)
        self.update_telemetry()

    def _apply_custom(self):
        c = self.cpu_slider.value()
        g = self.gpu_slider.value()
        set_fan_speed(c, g)
        self.update_telemetry()

    def update_telemetry(self):
        t = read_telemetry()
        if not t["driver_loaded"]:
            self.status_badge.setText(" DRIVER MISSING ")
            self.status_badge.setStyleSheet("background-color: #331010; color: #FF4444; border: 1px solid #882222;")
            return

        # Update cards
        self.card_cpu_fan.set_value(t["cpu_rpm"], f"Mode: {t['fan_mode']}")
        self.card_gpu_fan.set_value(t["gpu_rpm"], f"Mode: {t['fan_mode']}")

        # Temperature color-coding
        c_temp = t["cpu_temp"]
        c_color = "#44FF44" if c_temp < 60 else "#FFCC00" if c_temp < 78 else "#FF3333"
        self.card_cpu_temp.set_value(c_temp, "Package Temp", c_color)

        g_temp = t["gpu_temp"]
        g_color = "#44FF44" if g_temp < 60 else "#FFCC00" if g_temp < 78 else "#FF3333"
        if g_temp > 0:
            self.card_gpu_temp.set_value(g_temp, "Active", g_color)
        else:
            self.card_gpu_temp.set_value(0, "dGPU Standby (D3Cold)", "#777777")

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Acer Nitro Fan Management")
    win = NitroWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
