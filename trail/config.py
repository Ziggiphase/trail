"""Fixed constants and defaults. Tracked apps are chosen in the app's Settings window."""
import os
import socket

SAMPLE_SECONDS = 5          # how often we check the foreground window
IDLE_AFTER_SECONDS = 120    # no keyboard/mouse for this long = not working
SYNC_MINUTES = 10           # how often pending time is pushed to the cloud

# Hosted backend (Supabase). The publishable key is meant to ship inside apps:
# it can only do what the database's Row Level Security rules allow.
SUPABASE_URL = os.getenv("TRAIL_SUPABASE_URL", "https://eddyusnixdaaafqpleui.supabase.co")
SUPABASE_KEY = os.getenv("TRAIL_SUPABASE_KEY", "sb_publishable_gTQFLi-G2dXYI7wIJDQQgw_vr3hCwSO")
AUTH_PORT = 47261           # local port the browser returns to after sign-in
AUTH_REDIRECT = f"http://127.0.0.1:{AUTH_PORT}/callback"

# Updates and website
GITHUB_REPO = "Ziggiphase/trail"
WEBSITE_URL = "https://ziggiphase.github.io/trail/"
PRIVACY_URL = WEBSITE_URL + "privacy.html"
UPDATE_CHECK_HOURS = 6

DATABASE_URL = os.getenv("DATABASE_URL", "")   # only used to import old Neon history
DEVICE_NAME = os.getenv("DEVICE_NAME", socket.gethostname())

# Heatmap colour thresholds, in minutes of deep work per day.
LEVEL_THRESHOLDS_MIN = [1, 30, 90, 180]   # >0, >=30m, >=1.5h, >=3h
STREAK_MIN_MINUTES = 15                   # a day "counts" for the streak
