import openrgb
from openrgb.utils import RGBColor, DeviceType, ZoneType
from copy import deepcopy
import threading
import argparse
import signal
import sys

class VirtualLinearZone:
    def __init__(self, device):
        self.device = device

        base_custom = next(
            (m for m in device.modes if m.name.lower() == "custom"),
            None
        )

        if base_custom:
            custom = deepcopy(base_custom)

            custom.colors = None
            custom.colors_min = None
            custom.colors_max = None
            custom.speed = None
            custom.direction = None

            if custom.brightness_min is None or custom.brightness_max is None:
                custom.brightness = None
            else:
                custom.brightness = max(
                    min(custom.brightness, custom.brightness_max),
                    custom.brightness_min
                )

            device.set_mode(custom)

        self.colors = []
        for led in device.leds:
            if led.colors:
                self.colors.append(led.colors[0])
            else:
                self.colors.append(RGBColor(0, 0, 0))

    def show(self):
        self.device.set_colors(self.colors)

class OpenRGBClient:
    def __init__(self, address: str, port: int):
        self.address = address
        self.port = port
        try:
            self.client = openrgb.OpenRGBClient(address=self.address, port=self.port)
        except TimeoutError:
            print(f"Could not connect to OpenRGB server at {self.address}:{self.port}")
            exit(1)
        self.devices = self.client.devices

        self.effects = {
            "rainbow": self.effectRainbow,
            "rainbow-cycle": self.effectRainbowCycle,
            "alternate": self.effectAlternate,
        }

        self.effect_thread = None
        self.shutdown_event = threading.Event()
    
    def listDevices(self): # DEBUG METHOD
        for device in self.devices:
            print(f"Device: {device.name}")
            print(f"  Type: {device.type}")
            print(f"  Mode: {device.modes}")
            print(f"  Colors: {device.colors}")
            print(f"  Zones: {device.zones}")
    
    def selectDeviceByName(self, device_name: str):
        try:
            self.selected_device = self.client.get_devices_by_name(device_name)[0]
        except IndexError:
            print(f"No device found with name: {device_name}")
    
    def setColor(self, color: RGBColor):
        if hasattr(self, 'selected_device'):
            self.selected_device.set_color(color)
        else:
            print("No device selected. Use selectDeviceByName() to select a device first.")

    def _stop_current_effect(self):
        if self.effect_thread and self.effect_thread.is_alive():
            self.shutdown_event.set()
            self.effect_thread.join()
            self.effect_thread = None

    @staticmethod
    def threaded_effect(func):
        def wrapper(self, *args, **kwargs):
            self._stop_current_effect()

            self.shutdown_event.clear()

            # Store the thread so we can join later
            self.effect_thread = threading.Thread(
                target=func,
                args=(self, *args),
                kwargs=kwargs,
                daemon=False
            )
            self.effect_thread.start()

        return wrapper

    @threaded_effect
    def effectRainbowCycle(self):
        
        offset = 0
        while not self.shutdown_event.is_set():
            for i in range(len(self.zone.colors)):
                hue = (i * self.step + offset) % 360
                self.zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)
            self.zone.show()
            offset += 5
            self.shutdown_event.wait(0.05) # cooperative sleep
    
    @threaded_effect
    def effectAlternate(self):
        num_leds = len(self.zone.colors)
        offset = 0

        while not self.shutdown_event.is_set():
            for i in range(num_leds):
                if (i + offset) % 2 == 0:
                    self.zone.colors[i] = RGBColor(255, 0, 0)
                else:
                    self.zone.colors[i] = RGBColor(255, 255, 255)
            self.zone.show()
            offset += 1
            self.shutdown_event.wait(0.05)  # cooperative sleep

    def effectRainbow(self):
        for i, hue in enumerate(range(0, 360, self.step)):
            self.zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)
        self.zone.show()

    def setEffect(self, effect_name: str):
        if hasattr(self, 'selected_device'):
            # 1) Prefer real LINEAR zones if they exist
            zone = next(
                (
                    z for dev in self.client.devices
                    for z in dev.zones
                    if z.type == ZoneType.LINEAR
                ),
                None
            )

            # 2) Fallback: emulate a linear zone using per-LED Custom mode
            if zone is None:
                if not self.selected_device.leds:
                    print("Device has no LEDs to animate.")
                    return
                zone = VirtualLinearZone(self.selected_device)

            self.zone = zone
            print(f"Virtual zone with {len(self.zone.colors)} LEDs")
            self.step = int(360 / len(self.zone.colors))

            try:
                self.effects[effect_name]()
            except KeyError:
                raise ValueError(f"Unknown effect: {effect_name}")
        else:
            print("No device selected. Use selectDeviceByName() to select a device first.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenRGB Client")
    parser.add_argument("--address", default="localhost", help="OpenRGB server address")
    parser.add_argument("--port", type=int, default=6742, help="OpenRGB server port")
    parser.add_argument("--device", help="Device name to select")
    parser.add_argument("--effect", help="Effect to run")
    parser.add_argument("--color", nargs=3, type=int, metavar=("R", "G", "B"), help="Color to set (RGB values 0-255)")
    
    args = parser.parse_args()
    
    if not args.effect and not args.color:
        parser.error("Either --effect or --color must be specified")
    elif args.effect and args.color:
        parser.error("Cannot specify both --effect and --color")
    elif args.device is None:
        parser.error("--device is required")

    args = parser.parse_args()

    client = OpenRGBClient(args.address, args.port)

    def signal_handler(_sig, _frame):
        print("Shutting down...")
        client.shutdown_event.set()
        if client.effect_thread and client.effect_thread.is_alive():
            client.shutdown_event.set()
            client.effect_thread.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    client.selectDeviceByName(args.device)
    if args.effect:
        client.setEffect(args.effect)
        try:
            while True:
                client.shutdown_event.wait(1)
        except KeyboardInterrupt:
            signal_handler(None, None)
    elif args.color:
        color = RGBColor(args.color[0], args.color[1], args.color[2])
        client.setColor(color)
