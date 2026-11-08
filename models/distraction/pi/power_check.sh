uptime
for f in /proc/device-tree/chosen/power/*; do printf '%s: ' "$f"; od -An -tx4 "$f"; done
vcgencmd pmic_read_adc EXT5V_V
vcgencmd get_throttled
vcgencmd get_config usb_max_current_enable
dmesg | grep -iE 'voltage|undervolt|usb_max|current limit|power supply' | head -8
lsusb
ls /var/log/journal 2>/dev/null | head -2
