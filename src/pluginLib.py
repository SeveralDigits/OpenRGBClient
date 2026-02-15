from pathlib import Path
from typing import Dict, Optional, List, Callable
import json
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

class LoadStatus(Enum):
    """Plugin loading status"""
    SUCCESS = "success"
    FAILED = "failed"
    NOT_LOADED = "not_loaded"

@dataclass
class FunctionMetadata:
    """Metadata for a plugin function"""
    func: Callable
    name: str
    looped: bool
    plugin_module: object
    
    def __call__(self, *args, **kwargs):
        """Make the wrapper callable"""
        return self.func(*args, **kwargs)
    
    def __repr__(self):
        return f"FunctionMetadata(name={self.name}, looped={self.looped})"

@dataclass
class Plugin:
    """Represents a loaded plugin"""
    name: str
    version: str
    description: str
    author: str
    functions: Dict[str, FunctionMetadata]
    manifest: Dict
    module: object
    status: LoadStatus = LoadStatus.SUCCESS
    error: Optional[Exception] = None

class PluginManager:
    """Manages plugin discovery and loading"""
    
    def __init__(self, plugins_dir: Path = None):
        """
        Initialize the plugin manager
        
        Args:
            plugins_dir: Path to plugins directory (defaults to ./plugins)
        """
        self.plugins_dir = plugins_dir or Path(__file__).parent / "plugins"
        self._loaded: Dict[str, Plugin] = {}
        self._manifests: Dict[str, Path] = {}
        self._load_errors: Dict[str, Exception] = {}
        
        self._discover_plugins()
        self._load_all()
    
    def _discover_plugins(self) -> None:
        """Discover all available plugins by scanning manifest.json files"""
        if not self.plugins_dir.exists():
            print(f"Plugins directory not found: {self.plugins_dir}")
            return
        
        for manifest_path in sorted(self.plugins_dir.glob('*/manifest.json')):
            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
                    plugin_name = manifest.get('name')
                    if plugin_name:
                        self._manifests[plugin_name] = manifest_path
            except json.JSONDecodeError as e:
                self._load_errors[str(manifest_path)] = e
            except Exception as e:
                self._load_errors[str(manifest_path)] = e
    
    def _install_dependencies(self, plugin_name: str, dependencies: Dict[str, str]) -> None:
        """Install plugin dependencies using pip"""
        if not dependencies:
            return
        
        print(f"  Installing dependencies for {plugin_name}...")
        for package_name, version_spec in dependencies.items():
            try:
                pip_spec = f"{package_name}{version_spec}"
                print(f"    Installing {pip_spec}...", end=" ")
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pip_spec],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print("✓")
            except subprocess.CalledProcessError as e:
                print(f"✗")
                raise Exception(f"Failed to install {package_name}{version_spec}: {e}")
    
    def _load_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Load a single plugin by name"""
        if plugin_name not in self._manifests:
            return None
        
        manifest_path = self._manifests[plugin_name]
        
        try:
            # Read manifest
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Install dependencies before loading the plugin
            dependencies = manifest.get('dependencies', {})
            if dependencies:
                self._install_dependencies(plugin_name, dependencies)
            
            # Load the plugin module
            plugin_dir = manifest_path.parent
            main_file = manifest.get('main')
            
            if not main_file:
                raise ValueError(f"'main' not specified in manifest")
            
            plugin_file = plugin_dir / main_file
            
            if not plugin_file.exists():
                raise FileNotFoundError(f"Main file not found: {plugin_file}")
            
            # Import the module
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Extract functions from manifest
            functions = {}
            for func_spec in manifest.get('functions', []):
                func_name = func_spec.get('name')
                looped = func_spec.get('looped', False)
                
                if hasattr(module, func_name):
                    func = getattr(module, func_name)
                    functions[func_name] = FunctionMetadata(
                        func=func,
                        name=func_name,
                        looped=looped,
                        plugin_module=module
                    )
                else:
                    print(f"Function '{func_name}' not found in {plugin_name}")
            
            # Create Plugin object
            plugin = Plugin(
                name=manifest.get('name'),
                version=manifest.get('version', 'unknown'),
                description=manifest.get('description', ''),
                author=manifest.get('author', 'unknown'),
                functions=functions,
                manifest=manifest,
                module=module,
                status=LoadStatus.SUCCESS
            )
            
            return plugin
        
        except Exception as e:
            print(f"✗ Failed to load plugin '{plugin_name}': {e}")
            self._load_errors[plugin_name] = e
            return None
    
    def _load_all(self) -> None:
        """Load all discovered plugins"""
        print(f"Loading plugins from {self.plugins_dir}...")
        
        for plugin_name in self._manifests.keys():
            plugin = self._load_plugin(plugin_name)
            if plugin:
                self._loaded[plugin_name] = plugin
                func_count = len(plugin.functions)
                print(f"✓ {plugin_name} v{plugin.version} ({func_count} functions)")
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name"""
        return self._loaded.get(name)
    
    def get_all_plugins(self) -> Dict[str, Plugin]:
        """Get all loaded plugins"""
        return self._loaded.copy()
    
    def get_available_plugins(self) -> List[str]:
        """Get list of all available plugin names"""
        return list(self._manifests.keys())
    
    def get_status(self) -> Dict:
        """Get current loading status"""
        return {
            'loaded': len(self._loaded),
            'available': len(self._manifests),
            'failed': len(self._load_errors),
            'errors': self._load_errors,
            'plugins': {
                name: {
                    'version': plugin.version,
                    'functions': list(plugin.functions.keys()),
                    'looped': [f.name for f in plugin.functions.values() if f.looped]
                }
                for name, plugin in self._loaded.items()
            }
        }