#!/usr/bin/env python3

import os
import time
import signal
import sys
from collections import namedtuple

# Structure to hold previous measurements
Prev = namedtuple('Prev', (
    'cpu_idle', 'cpu_total',
    'disk_read', 'disk_write',
    'net_rx', 'net_tx'
))

prev = None

def read_cpu_times():
    """Read aggregated and idle CPU times from /proc/stat."""
    with open('/proc/stat', 'r') as f:
        fields = f.readline().split()
    # fields[1:] = user, nice, system, idle, iowait, irq, softirq, steal...
    vals = list(map(int, fields[1:8]))  # up to softirq inclusive
    idle = vals[3]
    total = sum(vals)
    return idle, total

def read_mem_percent():
    """Parse /proc/meminfo to calculate memory usage percentage."""
    with open('/proc/meminfo', 'r') as f:
        total_line = f.readline()
        free_line  = f.readline()
    total = int(total_line.split()[1])
    free  = int(free_line.split()[1])
    used = total - free
    return used * 100.0 / total

def read_disk_usage_percent(path='/'):
    """Return disk usage percentage for the given mount point."""
    st = os.statvfs(path)
    used  = (st.f_blocks - st.f_bfree) * st.f_frsize
    total = st.f_blocks * st.f_frsize
    return used * 100.0 / total

def read_disk_io():
    """Parse /proc/diskstats to sum read/write sectors for block devices."""
    read_sectors = write_sectors = 0
    with open('/proc/diskstats', 'r') as f:
        for line in f:
            parts = line.split()
            name = parts[2]
            if name.startswith(('sd', 'nvme', 'hd')):
                read_sectors  += int(parts[5])
                write_sectors += int(parts[9])
    # Convert sectors (512 B) to MB
    return read_sectors * 512 / 1024**2, write_sectors * 512 / 1024**2

def read_net_dev():
    """Sum received/transmitted bytes from /proc/net/dev (exclude lo)."""
    rx = tx = 0
    with open('/proc/net/dev', 'r') as f:
        f.readline()  # header
        f.readline()  # header
        for line in f:
            iface, data = line.split(':', 1)
            iface = iface.strip()
            if iface == 'lo':
                continue
            vals = list(map(int, data.split()))
            rx += vals[0]
            tx += vals[8]
    # Return in KB
    return rx / 1024, tx / 1024

def handle_sigint(sig, frame):
    """Handle Ctrl+C for graceful exit."""
    print()
    sys.exit(0)

def main():
    global prev
    signal.signal(signal.SIGINT, handle_sigint)

    # Initialize previous measurements
    idle0, total0 = read_cpu_times()
    rd0, wr0     = read_disk_io()
    rx0, tx0     = read_net_dev()
    prev = Prev(idle0, total0, rd0, wr0, rx0, tx0)

    while True:
        # CPU utilization
        idle1, total1 = read_cpu_times()
        d_idle  = idle1  - prev.cpu_idle
        d_total = total1 - prev.cpu_total
        cpu_pct = (1.0 - d_idle / d_total) * 100.0 if d_total else 0.0

        # Memory utilization
        ram_pct = read_mem_percent()

        # Disk usage
        disk_pct = read_disk_usage_percent('/')

        # Disk I/O rates
        rd1, wr1    = read_disk_io()
        rd_rate     = rd1 - prev.disk_read
        wr_rate     = wr1 - prev.disk_write

        # Network traffic rates
        rx1, tx1    = read_net_dev()
        rx_rate     = rx1 - prev.net_rx
        tx_rate     = tx1 - prev.net_tx

        # Update previous measurements
        prev = Prev(idle1, total1, rd1, wr1, rx1, tx1)

        # Build output line
        line = (
            f"CPU:{cpu_pct:5.1f}% "
            f"RAM:{ram_pct:5.1f}% "
            f"DISK:{disk_pct:5.1f}% "
            f"I/O R:{rd_rate:5.2f}MB/s W:{wr_rate:5.2f}MB/s "
            f"NET ↑{tx_rate:6.2f}KB/s ↓{rx_rate:6.2f}KB/s"
        )

        # Truncate if wider than terminal
        try:
            cols = os.get_terminal_size().columns
            if len(line) > cols:
                line = line[:cols-3] + '...'
        except OSError:
            pass  # not a real terminal

        print(line, end='\r', flush=True)
        time.sleep(1)

if __name__ == '__main__':
    main()
