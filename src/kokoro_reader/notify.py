"""Desktop notifications are disabled: playback/status belong in the dock.

Keep the shared function for existing CLI/service callers, including errors.
It must never start notify-send or contact a desktop notification service.
CLI errors still go to stderr and service errors to the journal.
"""


def notify(message, error=False):
    return None
