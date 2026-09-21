import os, requests
API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2").read().strip()
s = requests.Session()
r = s.post(f"{API}/api/auth/login", json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
print("login", r.status_code)
print("limits", s.get(f"{API}/api/admin/tracks/bulk-upload/limits").status_code)
with open("/tmp/qa_tone.mp3", "rb") as f:
    files = {"files": ("qa_tone.mp3", f, "audio/mpeg")}
    data = {"default_language": "english", "default_genre": "pop", "channel_slugs": "on_air"}
    up = s.post(f"{API}/api/admin/tracks/bulk-upload", files=files, data=data)
print("upload status", up.status_code)
print("upload body", up.text[:600])
