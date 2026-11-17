"""Fixed constants and defaults. Tracked apps are chosen in the app's Settings window."""
import os
import socket

from dotenv import load_dotenv

load_dotenv()

SAMPLE_SECONDS = 5          # how often we check the foreground window
IDLE_AFTER_SECONDS = 120    # no keyboard/mouse for this long = not working
SYNC_MINUTES = 10           # how often pending time is pushed to the cloud

DATABASE_URL = os.getenv("DATABASE_URL", "")   # postgres://... from Neon/Supabase
DEVICE_NAME = os.getenv("DEVICE_NAME", socket.gethostname())

# Heatmap colour thresholds, in minutes of deep work per day.
LEVEL_THRESHOLDS_MIN = [1, 30, 90, 180]   # >0, >=30m, >=1.5h, >=3h
STREAK_MIN_MINUTES = 15                   # a day "counts" for the streak
