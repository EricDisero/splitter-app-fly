# Fly.io Django Deployment Guide with Persistent Volume

This guide walks you through deploying a Django app on Fly.io using SQLite with a persistent volume. It's designed for when you're starting fresh or redeploying from scratch.

---

## 🚀 Fresh Deployment Checklist

### 1. Create the Volume First
Before deploying, create a volume to persist your SQLite database:

```bash
fly volumes create splitter_volume --region sea --size 1
```

- `splitter_volume` is the name of the volume.
- `--region sea` should match your app's primary region in `fly.toml`.
- `--size 1` gives you 1GB (minimum size).

---

### 2. `fly.toml` Configuration
Your `fly.toml` file should include:

```toml
app = "splitter-app"
primary_region = "sea"

[env]
  PORT = "8080"
  DJANGO_SETTINGS_MODULE = "splitter_django.settings"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0
  processes = ["app"]

[http_service.http_options]
  backend_timeout = "300s"

[processes]
  app = "gunicorn splitter_django.wsgi:application --workers=2 --threads=2 --timeout=300"

[vm]
  size = "shared-cpu-1x"
  memory = 2048

[mounts]
  source = "splitter_volume"
  destination = "/data"
```

---

### 3. Update `settings.py` in Django
Make sure your SQLite database points to the mounted volume path:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/data/db.sqlite3',
    }
}
```

---

### 4. First Deploy

```bash
fly deploy
```

> 🚨 IMPORTANT: Your app will deploy but the DB won’t be ready until you run migrations manually (next step).

---

## ⚖️ Migrate the Database

You have **two options**:

### Option A: Run Migration via One-Off Machine

```bash
fly machine run -a splitter-app --volume splitter_volume:/data --region sea -- bash -c "python manage.py migrate"
```

- This creates a one-off container with the volume attached.

### Option B: SSH into the App and Run Migrate

```bash
fly ssh console
```
Then inside the app:
```bash
python manage.py migrate
```

---

## 🚫 Do NOT Use This
```toml
[deploy]
  release_command = "python manage.py migrate"
```

> This doesn't work reliably with SQLite + volumes. It fails because the release phase can't access the volume.

---

## 🔄 Redeploying Later?
You don't need to re-create the volume. Just make sure it's mounted and the `DATABASES` setting still points to `/data/db.sqlite3`. Reuse the same volume.

---

## 🖇️ Stop / Start Behavior
- Machines will auto-stop when idle to save cost.
- When a machine starts again, the mounted volume persists.
- You **do not need to migrate again** unless the volume is deleted.

---

## 📄 Reference Commands

- Create volume:
```bash
fly volumes create splitter_volume --region sea --size 1
```

- Deploy:
```bash
fly deploy
```

- SSH in:
```bash
fly ssh console
```

- Run migration:
```bash
python manage.py migrate
```

- One-off migration:
```bash
fly machine run -a splitter-app --volume splitter_volume:/data --region sea -- bash -c "python manage.py migrate"
```

---

Keep this file as your go-to deployment checklist for your Fly.io + Django + SQLite app with persistent storage!

**** PS. Don't forget to add domain URLs to "Allowed Hosts" in settings.py for DNS! ****