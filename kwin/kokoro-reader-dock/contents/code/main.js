// Plasma 6: placement is done by the compositor, including on Wayland.
// No timers, focus changes, monitor reconfiguration, or global window rules.
function isReader(window) {
    const app = String(window.desktopFileName || "");
    const klass = String(window.resourceClass || "");
    return (app === "kokoro-reader" || klass === "kokoro-reader")
        && window.caption === "Kokoro Reader";
}

function attach(window) {
    if (!isReader(window)) return;
    let placing = false;
    function place() {
        if (placing) return;
        const frame = window.frameGeometry;
        // MaximizeArea respects Plasma panel struts and is per output.
        const area = workspace.clientArea(KWin.MaximizeArea, window);
        const x = Math.round(area.x + (area.width - frame.width) / 2);
        const y = area.y + 12;
        if (frame.x === x && frame.y === y) return;
        placing = true;
        window.frameGeometry = {x: x, y: y, width: frame.width, height: frame.height};
        placing = false;
    }
    window.frameGeometryChanged.connect(place);
    window.windowShown.connect(place);
    place();
}

workspace.windowAdded.connect(attach);
workspace.stackingOrder.forEach(attach);
