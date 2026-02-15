import openrgb
from openrgb.utils import RGBColor, DeviceType, ZoneType
from pathlib import Path
from copy import deepcopy
import pluginLib
import threading
import argparse
import signal
import sys

class CombinedLinearZone:
    def __init__(self, zones):
        self.zones = zones

        # Build one continuous color buffer
        self.colors = []
        for z in zones:
            # Initialize from current zone colors
            if hasattr(z, "colors") and z.colors:
                self.colors.extend(z.colors)
            else:
                # Fallback if needed
                self.colors.extend([RGBColor(0, 0, 0)] * len(z.leds))

    def show(self):
        index = 0

        for z in self.zones:
            led_count = len(z.leds)

            # Slice correct segment for this zone
            segment = self.colors[index:index + led_count]

            z.set_colors(segment)
            index += led_count

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

        self.effect_thread = None
        self.shutdown_event = threading.Event()

        #set up plugin manager and load effects
        plugins_dir = Path(__file__).parent.parent / "plugins"
        self.plugin_manager = pluginLib.PluginManager(plugins_dir=plugins_dir)
        self.effects = self._bundle_effects()
        self._print_available_effects()
    
    def _bundle_effects(self) -> dict:
        """Bundle all plugin functions into a single effects dictionary"""
        effects = {}
        
        for plugin_name, plugin in self.plugin_manager.get_all_plugins().items():
            for func_name, func_meta in plugin.functions.items():
                # Create a unique key: "plugin-name.function-name"
                effect_key = f"{plugin_name}.{func_name}"
                
                # Store the function reference directly (it's callable via FunctionMetadata)
                effects[effect_key] = func_meta
        
        return effects
    
    def _print_available_effects(self):
        print("Available effects:")
        for effect_name in self.effects.keys():
            print(f" - {effect_name}")

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

    def setEffect(self, effect_name: str):
        if hasattr(self, 'selected_device'):
            # Gather all LINEAR zones from the selected device
            linear_zones = [
                z for z in self.selected_device.zones
                if z.type == ZoneType.LINEAR
            ]

            if not linear_zones:
                # Fallback: emulate a linear zone using per-LED Custom mode
                if not self.selected_device.leds:
                    print("Device has no LEDs to animate.")
                    return
                zone = VirtualLinearZone(self.selected_device)
                self.zone = zone
                print(f"Using virtual zone with {len(self.zone.colors)} LEDs")

            elif len(linear_zones) == 1:
                zone = linear_zones[0]
                self.zone = zone
                print(f"Using real zone: {zone.name} ({len(zone.leds)} LEDs)")

            else:
                # Merge multiple LINEAR zones into one logical zone
                zone = CombinedLinearZone(linear_zones)
                self.zone = zone
                total_leds = sum(len(z.leds) for z in linear_zones)
                print(f"Merged {len(linear_zones)} zones into one ({total_leds} LEDs)")

            # Step is always LED count for plugin effects
            self.step = len(self.zone.colors)

            try:
                effect_func = self.effects[effect_name]
                if effect_func.looped:
                    self._stop_current_effect()
                    self.shutdown_event.clear()

                    # Store the thread so we can join later
                    self.effect_thread = threading.Thread(
                        target=effect_func,
                        args=(self.zone, self.step, self.shutdown_event),
                        daemon=False
                    )
                    self.effect_thread.start()
                else:
                    effect_func(self.zone, self.step, self.shutdown_event)
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
