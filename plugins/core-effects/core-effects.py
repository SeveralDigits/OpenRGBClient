from openrgb.utils import RGBColor

def rainbowCycle(zone, step, shutdown_event):
    offset = 0
    while not shutdown_event.is_set():
        for i in range(len(zone.colors)):
            hue = (i * step + offset) % 360
            zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)
        zone.show()
        offset += 5
        shutdown_event.wait(0.05) # cooperative sleep

def alternate(zone, step, shutdown_event):
    num_leds = len(zone.colors)
    offset = 0

    while not shutdown_event.is_set():
        for i in range(num_leds):
            if (i + offset) % 2 == 0:
                zone.colors[i] = RGBColor(255, 0, 0)
            else:
                zone.colors[i] = RGBColor(255, 255, 255)
        zone.show()
        offset += 1
        shutdown_event.wait(1)  # cooperative sleep

def rainbow(zone, step, shutdown_event):
    for i, hue in enumerate(range(0, 360, step)):
        zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)
    zone.show()