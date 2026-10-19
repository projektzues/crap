# Roku Launcher

A simpler launcher for your Roku TV: big app tiles and a few remote buttons, in your browser or on your phone.

It runs on any computer on the same Wi-Fi as the TV. It finds the TV automatically and needs only Python 3, with nothing to install.

## Setup (once, on the TV)
Settings → System → Advanced system settings → **Control by mobile apps** → Network access → **Default** (or **Permissive**).

## Run
```
python3 roku_launcher.py
```
Open http://localhost:8080. To use it on your phone, open `http://<this-computer's-IP>:8080`.

Options:
- `--list` – just show the Rokus found on your network
- `--ip 192.168.1.50` – skip discovery and use this TV
- `--only "Netflix,YouTube,Hulu"` – show only these apps, in this order
- `--port 9000` – serve on a different port

If discovery finds nothing, look up the TV's IP under Settings → Network → About and pass `--ip`.
