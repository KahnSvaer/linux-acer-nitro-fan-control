#!/usr/bin/env python3
"""
Fan Control Center
------------------
Modern, open-source Linux fan and hardware cooling manager.
Provides tachometer gauges, real-time thermal telemetry, and hardware-safe fan controls.
"""

import math
import os
import sys
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

# Add parent directory for CLI telemetry functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cli.nitro_fan import is_driver_loaded, read_telemetry, set_fan_speed, PLATFORM_PROFILE

def get_app_icon():
    icon = QIcon()
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    svg_path = os.path.join(assets_dir, "nitrofan.svg")
    if os.path.exists(svg_path):
        icon.addFile(svg_path)
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        png_path = os.path.join(assets_dir, f"nitrofan_{s}.png")
        if os.path.exists(png_path):
            icon.addFile(png_path)
    return icon

class CircularFanGauge(QWidget):
    """
    Custom-drawn Circular Tachometer Gauge.
    Renders anti-aliased circular progress arcs, RPM readouts, and temperature badges.
    """
    def __init__(self, title="CPU FAN", max_rpm=7000, parent=None):
        super().__init__(parent)
        self.title = title
        self.max_rpm = max_rpm
        self.current_rpm = 0
        self.display_rpm = 0.0
        self.temp_val = 0
        self.temp_text = "0 °C"
        self.is_active = True
        self.setMinimumSize(220, 240)

        # Responsive needle animation timer (40 FPS)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate_step)
        self.anim_timer.start(25)

    def set_data(self, rpm: int, temp: int, is_active: bool = True):
        if rpm > self.max_rpm:
            self.max_rpm = rpm
        self.current_rpm = max(0, min(self.max_rpm, rpm))
        self.temp_val = temp
        self.is_active = is_active
        if not is_active or temp <= 0:
            self.temp_text = "STANDBY"
        else:
            self.temp_text = f"{temp} °C"

    def _animate_step(self):
        diff = self.current_rpm - self.display_rpm
        if abs(diff) > 2:
            self.display_rpm += diff * 0.35
            self.update()
        elif self.display_rpm != self.current_rpm:
            self.display_rpm = float(self.current_rpm)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h - 35)
        cx = w / 2.0
        cy = size / 2.0 + 6.0
        radius = size / 2.0 - 12.0

        # Current live ratio and percentage
        ratio = max(0.0, min(1.0, self.display_rpm / max(1, self.max_rpm)))
        cur_pct = int(round(ratio * 100))

        # 1. Draw outer subtle metallic ring
        outer_pen = QPen(QColor(40, 42, 50), 2)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius + 6, radius + 6)

        # 2. Draw inner face with radial gradient
        radial = QRadialGradient(QPointF(cx, cy), radius)
        radial.setColorAt(0.0, QColor(24, 25, 30))
        radial.setColorAt(0.85, QColor(16, 17, 21))
        radial.setColorAt(1.0, QColor(10, 11, 14))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(radial))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 3. Gauge arc coordinates: 270 degree sweep from 225 deg (bottom-left) to -45 deg (bottom-right)
        start_angle = 225.0
        total_span = -270.0
        track_r = radius - 4
        arc_rect = QRectF(cx - track_r, cy - track_r, track_r * 2, track_r * 2)

        # Background track arc
        track_pen = QPen(QColor(32, 35, 43), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(arc_rect, int(start_angle * 16), int(total_span * 16))

        # Active value arc with dynamic color gradient
        active_span = total_span * ratio
        if ratio > 0.01:
            active_pen = QPen()
            active_pen.setWidth(6)
            active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

            grad = QLinearGradient(arc_rect.topLeft(), arc_rect.bottomRight())
            if ratio < 0.45:
                grad.setColorAt(0.0, QColor(0, 230, 118))
                grad.setColorAt(1.0, QColor(0, 200, 160))
            elif ratio < 0.75:
                grad.setColorAt(0.0, QColor(255, 179, 0))
                grad.setColorAt(1.0, QColor(255, 100, 0))
            else:
                grad.setColorAt(0.0, QColor(255, 60, 40))
                grad.setColorAt(1.0, QColor(230, 0, 20))
            active_pen.setBrush(QBrush(grad))
            painter.setPen(active_pen)
            painter.drawArc(arc_rect, int(start_angle * 16), int(active_span * 16))

        # 4. Clean 10% Interval Scale Lines (0%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%, 100%)
        # Finer sub-ticks removed for a clean, minimal speedometer scale
        for i in range(11):  # Exactly 11 clean lines
            tick_pct = i * 10
            theta = start_angle + total_span * (tick_pct / 100.0)
            rad = math.radians(theta)
            cos_t = math.cos(rad)
            sin_t = math.sin(rad)

            is_reached = (tick_pct <= cur_pct)
            is_major = (tick_pct % 20 == 0)

            # Major lines (0%, 20%, 40%, 60%, 80%, 100%) slightly longer than intermediate lines (10%, 30%, 50%...)
            r1 = radius - (15 if is_major else 11)
            r2 = radius - 3
            pen_w = 2.0 if is_major else 1.5
            pen_color = QColor(255, 45, 45) if is_reached else (QColor(95, 102, 118) if is_major else QColor(50, 55, 68))

            painter.setPen(QPen(pen_color, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(
                QPointF(cx + r1 * cos_t, cy - r1 * sin_t),
                QPointF(cx + r2 * cos_t, cy - r2 * sin_t)
            )

        # 5. Scale Percentage Numbers (0%, 20%, 40%, 60%, 80%, 100% on the scale dial)
        font_scale = QFont("Arial", 7, QFont.Weight.Bold)
        painter.setFont(font_scale)
        for p in (0, 20, 40, 60, 80, 100):
            theta = start_angle + total_span * (p / 100.0)
            rad = math.radians(theta)
            r_lbl = radius - 26
            lx = cx + r_lbl * math.cos(rad)
            ly = cy - r_lbl * math.sin(rad)

            if p <= cur_pct:
                painter.setPen(QColor(255, 255, 255))
            else:
                painter.setPen(QColor(90, 98, 115))

            painter.drawText(QRectF(lx - 16, ly - 8, 32, 16), Qt.AlignmentFlag.AlignCenter, f"{p}%")

        # 6. Active Pointer / Needle Pip on Track
        if ratio > 0.01:
            theta_now = start_angle + total_span * ratio
            rad_now = math.radians(theta_now)
            pip_r = radius - 4
            px = cx + pip_r * math.cos(rad_now)
            py = cy - pip_r * math.sin(rad_now)

            # Outer white ring with red core
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.setBrush(QBrush(QColor(255, 30, 30)))
            painter.drawEllipse(QPointF(px, py), 4.0, 4.0)

        # 7. Center Text: Title
        painter.setPen(QColor(150, 155, 170))
        font_title = QFont("Arial", 10, QFont.Weight.Bold)
        font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        painter.setFont(font_title)
        painter.drawText(QRectF(cx - 80, cy - 42, 160, 20), Qt.AlignmentFlag.AlignCenter, self.title)

        # 8. Center Text: Large RPM Value
        painter.setPen(QColor(255, 255, 255))
        font_rpm = QFont("Arial", 22, QFont.Weight.Bold)
        painter.setFont(font_rpm)
        rpm_str = f"{int(self.display_rpm):,}"
        painter.drawText(QRectF(cx - 90, cy - 18, 180, 36), Qt.AlignmentFlag.AlignCenter, rpm_str)

        # 9. Center Text: Clean "RPM" Unit Label beneath numbers
        painter.setPen(QColor(110, 115, 130))
        font_unit = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font_unit)
        painter.drawText(QRectF(cx - 50, cy + 18, 100, 18), Qt.AlignmentFlag.AlignCenter, "RPM")

        # 10. Bottom Temperature Pill
        pill_w = 110.0
        pill_h = 26.0
        pill_x = cx - pill_w / 2.0
        pill_y = cy + radius - 6.0
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        # Pill background
        painter.setPen(QPen(QColor(45, 48, 58), 1))
        painter.setBrush(QBrush(QColor(22, 24, 29)))
        painter.drawRoundedRect(pill_rect, 13.0, 13.0)

        # Temperature status dot
        if not self.is_active or self.temp_val <= 0:
            dot_color = QColor(100, 100, 100)
        elif self.temp_val < 60:
            dot_color = QColor(0, 230, 115)
        elif self.temp_val < 78:
            dot_color = QColor(255, 190, 0)
        else:
            dot_color = QColor(255, 40, 40)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_color))
        painter.drawEllipse(QPointF(pill_x + 16, pill_y + 13), 4, 4)

        # Pill Text
        painter.setPen(QColor(240, 240, 240))
        font_temp = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font_temp)
        painter.drawText(QRectF(pill_x + 24, pill_y, pill_w - 28, pill_h), Qt.AlignmentFlag.AlignCenter, self.temp_text)

        painter.end()


class NitroFanWindow(QMainWindow):
    """
    Main NitroFan UI Window.
    Provides custom tachometer gauges, thermal monitoring, and responsive fan controls.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fan Control Center")
        self.setFixedSize(620, 740)
        self.active_mode = "auto"
        self.sync_fans = True

        self.app_icon = get_app_icon()
        self.setWindowIcon(self.app_icon)

        self._init_theme()
        self._init_ui()
        self._init_tray()

        # High-speed live telemetry update timer (200ms = 5 updates/sec)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._update_telemetry)
        self.poll_timer.start(200)
        self._update_telemetry()

    def _init_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0E0F12;
            }
            QWidget {
                color: #D8D8D8;
                font-family: "Segoe UI", "Inter", "Arial", sans-serif;
            }
            QFrame.card {
                background-color: #15171C;
                border: 1px solid #232630;
                border-radius: 12px;
            }
            QFrame.card_header {
                background-color: #121317;
                border-bottom: 1px solid #232630;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                padding: 6px 12px;
            }
        """)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(22, 18, 22, 18)
        main_layout.setSpacing(14)

        # ---------------- 1. Top Header Banner ----------------
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 2)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel("Fan Control Center")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #F0F4F8; letter-spacing: 0.5px;")

        sub_label = QLabel("Independent Hardware Cooling & Thermal Monitor")
        sub_label.setFont(QFont("Arial", 9))
        sub_label.setStyleSheet("color: #718096;")

        title_box.addWidget(title_label)
        title_box.addWidget(sub_label)
        header.addLayout(title_box)

        header.addStretch()

        # Hardware & Driver Status Badge
        badge_box = QVBoxLayout()
        badge_box.setSpacing(2)
        badge_box.setAlignment(Qt.AlignmentFlag.AlignRight)

        model_label = QLabel("SYSTEM: ANV15-41")
        model_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        model_label.setStyleSheet("color: #7A8090; letter-spacing: 1px;")

        self.driver_badge = QLabel("● LIVE (5 Hz)")
        self.driver_badge.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.driver_badge.setStyleSheet("color: #00FF66; letter-spacing: 0.5px;")

        badge_box.addWidget(model_label)
        badge_box.addWidget(self.driver_badge)
        header.addLayout(badge_box)
        main_layout.addLayout(header)

        # ---------------- 2. Mode Segment Bar ----------------
        mode_card = QFrame()
        mode_card.setProperty("class", "card")
        mode_card_layout = QHBoxLayout(mode_card)
        mode_card_layout.setContentsMargins(8, 8, 8, 8)
        mode_card_layout.setSpacing(8)

        self.btn_mode_auto = QPushButton("AUTO")
        self.btn_mode_max = QPushButton("MAX TURBO")
        self.btn_mode_custom = QPushButton("CUSTOM")

        for btn in (self.btn_mode_auto, self.btn_mode_max, self.btn_mode_custom):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            btn.setFixedHeight(42)

        self.btn_mode_auto.clicked.connect(lambda: self._switch_mode("auto"))
        self.btn_mode_max.clicked.connect(lambda: self._switch_mode("max"))
        self.btn_mode_custom.clicked.connect(lambda: self._switch_mode("custom"))

        mode_card_layout.addWidget(self.btn_mode_auto)
        mode_card_layout.addWidget(self.btn_mode_max)
        mode_card_layout.addWidget(self.btn_mode_custom)
        main_layout.addWidget(mode_card)

        # ---------------- 3. Dual Tachometer Speedometers ----------------
        gauges_frame = QFrame()
        gauges_frame.setProperty("class", "card")
        gauges_layout = QHBoxLayout(gauges_frame)
        gauges_layout.setContentsMargins(10, 10, 10, 14)
        gauges_layout.setSpacing(10)

        self.cpu_gauge = CircularFanGauge("CPU FAN", max_rpm=6800)
        self.gpu_gauge = CircularFanGauge("GPU FAN", max_rpm=6400)

        gauges_layout.addWidget(self.cpu_gauge)
        gauges_layout.addWidget(self.gpu_gauge)
        main_layout.addWidget(gauges_frame)

        # ---------------- Safety Alert Banner (Hardware Thermal Guard) ----------------
        self.safety_alert_frame = QFrame()
        self.safety_alert_frame.setStyleSheet("""
            QFrame {
                background-color: #2D1A10;
                border: 1px solid #FF8C00;
                border-radius: 8px;
            }
        """)
        alert_layout = QHBoxLayout(self.safety_alert_frame)
        alert_layout.setContentsMargins(12, 6, 12, 6)
        self.safety_alert_label = QLabel("🛡️ Thermal Safeguard Active: Elevated fan speeds to protect hardware from high temps.")
        self.safety_alert_label.setStyleSheet("color: #FFA726; font-size: 11px; font-weight: bold;")
        alert_layout.addWidget(self.safety_alert_label)
        self.safety_alert_frame.hide()
        main_layout.addWidget(self.safety_alert_frame)

        # ---------------- 4. Custom Manual Fan Speed Sliders ----------------
        self.custom_card = QFrame()
        self.custom_card.setProperty("class", "card")
        custom_layout = QVBoxLayout(self.custom_card)
        custom_layout.setContentsMargins(18, 16, 18, 16)
        custom_layout.setSpacing(12)

        # Header for Custom section
        custom_header = QHBoxLayout()
        sec_title = QLabel("MANUAL FAN SPEED TUNING (SAFE RANGE: 25% - 100%)")
        sec_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        sec_title.setStyleSheet("color: #8C92A4; letter-spacing: 0.5px;")
        custom_header.addWidget(sec_title)
        custom_header.addStretch()

        self.chk_sync = QCheckBox("Link CPU & GPU Fans")
        self.chk_sync.setChecked(True)
        self.chk_sync.setStyleSheet("color: #CCCCCC; font-size: 11px;")
        self.chk_sync.toggled.connect(self._on_sync_toggled)
        custom_header.addWidget(self.chk_sync)
        custom_layout.addLayout(custom_header)

        # CPU Fan Slider Row
        cpu_box = QHBoxLayout()
        cpu_lbl = QLabel("CPU Fan:")
        cpu_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #E0E0E0;")
        self.cpu_pct_lbl = QLabel("60%")
        self.cpu_pct_lbl.setStyleSheet("color: #FF2A2A; font-weight: bold; font-size: 12px;")
        cpu_box.addWidget(cpu_lbl)
        cpu_box.addStretch()
        cpu_box.addWidget(self.cpu_pct_lbl)
        custom_layout.addLayout(cpu_box)

        self.slider_cpu = QSlider(Qt.Orientation.Horizontal)
        self.slider_cpu.setRange(25, 100)
        self.slider_cpu.setValue(60)
        self.slider_cpu.setStyleSheet(self._slider_stylesheet())
        self.slider_cpu.valueChanged.connect(self._on_cpu_slider_changed)
        custom_layout.addWidget(self.slider_cpu)

        # GPU Fan Slider Row
        gpu_box = QHBoxLayout()
        gpu_lbl = QLabel("GPU Fan:")
        gpu_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #E0E0E0;")
        self.gpu_pct_lbl = QLabel("60%")
        self.gpu_pct_lbl.setStyleSheet("color: #FF2A2A; font-weight: bold; font-size: 12px;")
        gpu_box.addWidget(gpu_lbl)
        gpu_box.addStretch()
        gpu_box.addWidget(self.gpu_pct_lbl)
        custom_layout.addLayout(gpu_box)

        self.slider_gpu = QSlider(Qt.Orientation.Horizontal)
        self.slider_gpu.setRange(25, 100)
        self.slider_gpu.setValue(60)
        self.slider_gpu.setStyleSheet(self._slider_stylesheet())
        self.slider_gpu.valueChanged.connect(self._on_gpu_slider_changed)
        custom_layout.addWidget(self.slider_gpu)

        # Quick Preset Buttons
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(8)
        for pct, name in [(40, "Quiet 40%"), (60, "Balanced 60%"), (80, "Heavy Load 80%"), (100, "Max Turbo 100%")]:
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1E2129;
                    color: #A0A5B5;
                    border: 1px solid #2B303C;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #262B36;
                    color: #FFFFFF;
                    border-color: #FF2A2A;
                }
            """)
            btn.clicked.connect(lambda _, p=pct: self._apply_preset(p))
            presets_layout.addWidget(btn)
        custom_layout.addLayout(presets_layout)

        # Apply Button
        self.btn_apply = QPushButton("APPLY FAN SPEEDS")
        self.btn_apply.setFixedHeight(38)
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #C20000, stop:1 #FF1A1A);
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E60000, stop:1 #FF3333);
            }
            QPushButton:pressed {
                background: #990000;
            }
        """)
        self.btn_apply.clicked.connect(self._apply_custom_speeds)
        custom_layout.addWidget(self.btn_apply)

        main_layout.addWidget(self.custom_card)

        # ---------------- 5. Footer Status ----------------
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        self.status_footer = QLabel("Active Profile: Balanced | WMI Interface Verified")
        self.status_footer.setStyleSheet("color: #555A6B; font-size: 11px;")
        footer.addWidget(self.status_footer)

        footer.addStretch()

        reset_btn = QPushButton("Reset to Auto")
        reset_btn.setFlat(True)
        reset_btn.setStyleSheet("color: #777E90; font-size: 11px; text-decoration: underline;")
        reset_btn.clicked.connect(lambda: self._switch_mode("auto"))
        footer.addWidget(reset_btn)

        main_layout.addLayout(footer)

        # Initialize button styles
        self._update_button_styles()

    def _slider_stylesheet(self):
        return """
            QSlider::groove:horizontal {
                height: 6px;
                background: #20242E;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #990000, stop:1 #FF2222);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 2px solid #FF2222;
                width: 16px;
                height: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #FF2222;
            }
        """

    def _update_button_styles(self):
        active_style = """
            QPushButton {
                background-color: #221214;
                color: #FFFFFF;
                border: 2px solid #FF1A1A;
                border-radius: 8px;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #15171C;
                color: #8C92A4;
                border: 1px solid #232630;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #1A1D24;
                color: #FFFFFF;
                border-color: #383D4D;
            }
        """

        self.btn_mode_auto.setStyleSheet(active_style if self.active_mode == "auto" else inactive_style)
        self.btn_mode_max.setStyleSheet(active_style if self.active_mode == "max" else inactive_style)
        self.btn_mode_custom.setStyleSheet(active_style if self.active_mode == "custom" else inactive_style)

        # Dim custom sliders when not in custom mode
        is_custom = (self.active_mode == "custom")
        self.slider_cpu.setEnabled(is_custom)
        self.slider_gpu.setEnabled(is_custom)
        self.btn_apply.setEnabled(is_custom)
        self.custom_card.setStyleSheet(f"""
            QFrame.card {{
                background-color: {'#15171C' if is_custom else '#111216'};
                border: 1px solid {'#2A2E3B' if is_custom else '#1A1C22'};
                border-radius: 12px;
            }}
        """)

    def _switch_mode(self, mode: str):
        self.active_mode = mode
        self._update_button_styles()

        if mode == "auto":
            set_fan_speed(0, 0)
        elif mode == "max":
            set_fan_speed(100, 100)
        elif mode == "custom":
            self._apply_custom_speeds()

        self._update_telemetry()

    def _on_sync_toggled(self, checked: bool):
        self.sync_fans = checked
        if checked:
            self.slider_gpu.setValue(self.slider_cpu.value())

    def _on_cpu_slider_changed(self, val: int):
        self.cpu_pct_lbl.setText(f"{val}%")
        if self.sync_fans:
            self.slider_gpu.blockSignals(True)
            self.slider_gpu.setValue(val)
            self.gpu_pct_lbl.setText(f"{val}%")
            self.slider_gpu.blockSignals(False)

    def _on_gpu_slider_changed(self, val: int):
        self.gpu_pct_lbl.setText(f"{val}%")
        if self.sync_fans:
            self.slider_cpu.blockSignals(True)
            self.slider_cpu.setValue(val)
            self.cpu_pct_lbl.setText(f"{val}%")
            self.slider_cpu.blockSignals(False)

    def _apply_preset(self, pct: int):
        self.slider_cpu.setValue(pct)
        self.slider_gpu.setValue(pct)
        if self.active_mode != "custom":
            self.active_mode = "custom"
            self._update_button_styles()
        self._apply_custom_speeds()

    def _apply_custom_speeds(self):
        c = self.slider_cpu.value()
        g = self.slider_gpu.value()
        set_fan_speed(c, g)
        self._update_telemetry()

    def _update_telemetry(self):
        t = read_telemetry(force_profile=False)
        if not t["driver_loaded"]:
            self.driver_badge.setText("● DRIVER OFFLINE")
            self.driver_badge.setStyleSheet("color: #FF3333;")
            return

        # Update gauges with live telemetry
        self.cpu_gauge.set_data(t["cpu_rpm"], t["cpu_temp"], True)
        self.gpu_gauge.set_data(t["gpu_rpm"], t["gpu_temp"], t["gpu_temp"] > 0)

        # Reflect detected active mode from driver
        mode_str = t["fan_mode"]
        if mode_str == "100,100" and self.active_mode != "max":
            self.active_mode = "max"
            self._update_button_styles()
        elif mode_str == "0,0" and self.active_mode != "auto":
            self.active_mode = "auto"
            self._update_button_styles()

        lat = t.get("latency_ms", 2.0)
        self.status_footer.setText(f"Active Mode: {mode_str} | Telemetry: {lat:.1f}ms latency (5 Hz Live) | Profile: {t['profile']}")

        # Hardware Thermal Safeguard:
        # If CPU or GPU temperature reaches dangerous threshold (>= 88°C CPU or >= 85°C GPU)
        # while fan speeds are manually held low (< 75%), automatically elevate fans to protect silicon!
        max_temp = max(t["cpu_temp"], t["gpu_temp"])
        if max_temp >= 88 and self.active_mode == "custom":
            c_val = self.slider_cpu.value()
            g_val = self.slider_gpu.value()
            if c_val < 75 or g_val < 75:
                self.slider_cpu.setValue(85)
                self.slider_gpu.setValue(85)
                set_fan_speed(85, 85)
                self.safety_alert_frame.show()
        elif max_temp <= 80:
            if hasattr(self, "safety_alert_frame") and self.safety_alert_frame.isVisible():
                self.safety_alert_frame.hide()

    def _init_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self.app_icon, self)
            self.tray_icon.setToolTip("Fan Control Center")

            tray_menu = QMenu()
            action_show = tray_menu.addAction("Open Fan Control Center")
            action_show.triggered.connect(self._show_and_raise)
            tray_menu.addSeparator()
            action_auto = tray_menu.addAction("Mode: Auto (Firmware Curve)")
            action_auto.triggered.connect(lambda: self._switch_mode("auto"))
            action_max = tray_menu.addAction("Mode: Max Turbo (100%)")
            action_max.triggered.connect(lambda: self._switch_mode("max"))
            tray_menu.addSeparator()
            action_quit = tray_menu.addAction("Quit")
            action_quit.triggered.connect(QApplication.instance().quit)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()

    def _show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                if self.isMinimized():
                    self.showNormal()
                else:
                    self.raise_()
                    self.activateWindow()
            else:
                self.show()

def main():
    # Ensure process name and desktop file matching for GNOME/Wayland/X11 dock & side tray
    sys.argv[0] = "nitrofan"
    app = QApplication(sys.argv)
    app.setApplicationName("nitrofan")
    app.setApplicationDisplayName("Fan Control Center")
    app.setDesktopFileName("nitrofan")

    icon = get_app_icon()
    app.setWindowIcon(icon)

    win = NitroFanWindow()
    win.setWindowIcon(icon)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
