from openrgb.utils import RGBColor


def rainbowCycle(zone, led_count, shutdown_event):
    offset = 0

    while not shutdown_event.is_set():
        for i in range(led_count):
            hue = ((i * 360) // led_count + offset) % 360
            zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)

        zone.show()
        offset = (offset + 5) % 360
        shutdown_event.wait(0.05)


def alternate(zone, led_count, shutdown_event):
    offset = 0

    while not shutdown_event.is_set():
        for i in range(led_count):
            if (i + offset) % 2 == 0:
                zone.colors[i] = RGBColor(255, 0, 0)
            else:
                zone.colors[i] = RGBColor(255, 255, 255)

        zone.show()
        offset += 1
        shutdown_event.wait(1)


def rainbow(zone, led_count, shutdown_event):
    for i in range(led_count):
        hue = (i * 360) // led_count
        zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)

    zone.show()
