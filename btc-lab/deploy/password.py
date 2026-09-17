"""Generate dashboard credentials locally. Never paste them into issues or Git."""
import hashlib
import secrets
password=secrets.token_urlsafe(24)
print('Dashboard password (save privately):',password)
print('LAB_PASSWORD_SHA256='+hashlib.sha256(password.encode()).hexdigest())
