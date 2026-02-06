import openrgb
from openrgb.utils import RGBColor, DeviceType, ZoneType
import threading
import signal
import sys

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
            self.zone = next(z for dev in self.client.ee_devices for z in dev.zones if z.type == ZoneType.LINEAR)
            self.step = int(360/len(self.zone.colors))
            try:
                self.effects[effect_name]()
            except KeyError:
                raise ValueError(f"Unknown effect: {effect_name}")
        else:
            print("No device selected. Use selectDeviceByName() to select a device first.")

if __name__ == "__main__":
    client = OpenRGBClient("localhost", 6742)

    def signal_handler(sig, frame):
        print("Shutting down...")
        client.shutdown_event.set()
        if client.effect_thread and client.effect_thread.is_alive():
            client.shutdown_event.set()
            client.effect_thread.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    client.selectDeviceByName("B550 GAMING X V2")
    client.setEffect("rainbow-cycle")

    try:
        while True:
            client.shutdown_event.wait(1)
    except KeyboardInterrupt:
        signal_handler(None, None)