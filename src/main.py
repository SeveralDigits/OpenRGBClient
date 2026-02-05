import time
import openrgb
from openrgb.utils import RGBColor, DeviceType, ZoneType
import threading

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
    
    def listDevices(self): # DEBUG METHOD
        for device in self.devices:
            print(f"Device: {device.name}")
            print(f"  Type: {device.type}")
            print(f"  Mode: {device.modes}")
            print(f"  Colors: {device.colors}")
            print(f"  Zones: {device.zones}")
    
    def selectDeviceByName(self, device_name: str):
        self.selected_device = self.client.get_devices_by_name(device_name)[0]
    
    def setColor(self, color: RGBColor):
        if hasattr(self, 'selected_device'):
            self.selected_device.set_color(color)
        else:
            print("No device selected. Use selectDeviceByName() to select a device first.")

    def setEffect(self, effect_name: str):
        if hasattr(self, 'selected_device'):
            zone = next(z for dev in self.client.ee_devices for z in dev.zones if z.type == ZoneType.LINEAR)
            step = int(360/len(zone.colors))
            if effect_name == "rainbow":
                for i, hue in enumerate(range(0, 360, step)):
                    zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)
                    zone.show()
            elif effect_name == "rainbow-cycle":
                offset = 0
                while True:
                    for i in range(len(zone.colors)):
                        hue = (i * 30 + offset) % 360
                        zone.colors[i] = RGBColor.fromHSV(hue, 100, 100)
                        zone.show()
                        offset += 5
                        time.sleep(0.05)
            elif effect_name == "alternate":
                num_leds = len(zone.colors)
                offset = 0

                while True:
                    for i in range(num_leds):
                        if (i + offset) % 2 == 0:
                            zone.colors[i] = RGBColor(255, 0, 0)
                        else:
                            zone.colors[i] = RGBColor(255, 255, 255)
                    zone.show()
                    offset += 1
                    time.sleep(0.1)
        else:
            print("No device selected. Use selectDeviceByName() to select a device first.")

if __name__ == "__main__":
    client = OpenRGBClient("localhost", 6742)
    client.selectDeviceByName("B550 GAMING X V2")
    client.setEffect("rainbow-cycle")