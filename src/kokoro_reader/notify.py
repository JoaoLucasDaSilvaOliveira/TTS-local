import subprocess


def notify(message, error=False):
    try:
        subprocess.Popen(["notify-send", "--app-name=Kokoro Reader", "--urgency=" + ("critical" if error else "normal"),
                          "Kokoro Reader", str(message)[:500]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
