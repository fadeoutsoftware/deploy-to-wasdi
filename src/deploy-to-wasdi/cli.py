import os
import shutil
import yaml
import argparse
import importlib.util
from pathlib import Path

def load_config(config_path: str) -> dict:
    """Loads the YAML configuration file."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    with open(config_file, 'r') as file:
        return yaml.safe_load(file)

def clean_unnecessary_files(target_dir: Path, exclude_patterns: list):
    """Removes files and directories matching the exclude patterns."""
    for pattern in exclude_patterns:
        # rglob finds all matches recursively
        for path in list(target_dir.rglob(pattern)):
            if not path.exists():
                continue # Skip if already deleted (e.g., inside a deleted folder)
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

def prepare_deployment(config_file: str):
    """Executes Phase 1: Prepare"""
    config = load_config(config_file)
    
    build_dir = Path(config['build_dir'])
    source_dir = Path(config['source_dir'])
    
    print(f"🚀 Starting deployment preparation for: {config['project_name']}")
    
    if build_dir.exists():
        shutil.rmtree(build_dir)
        
    print(f"📂 Copying source code from {source_dir} to {build_dir}...")
    shutil.copytree(source_dir, build_dir)
    
    # Rename entry point
    entry_config = config.get('entry_point')
    if entry_config:
        entry_source = build_dir / entry_config['source']
        entry_target = build_dir / entry_config['target']
        
        if entry_source.exists():
            entry_source.rename(entry_target)
            print(f"🔄 Renamed {entry_source.name} to {entry_target.name}")
        else:
            print(f"⚠️  Warning: Entry point {entry_source.name} not found!")

    # Copy custom local modules
    custom_modules = config.get('custom_modules', [])
    if custom_modules:
        print("📦 Copying custom modules by path...")
        for mod_path_str in custom_modules:
            mod_path = Path(mod_path_str)
            if mod_path.is_file():
                shutil.copy2(mod_path, build_dir / mod_path.name)
                print(f"   - Added file: {mod_path.name}")
            elif mod_path.is_dir():
                shutil.copytree(mod_path, build_dir / mod_path.name, dirs_exist_ok=True)
                print(f"   - Added directory: {mod_path.name}")
            else:
                print(f"⚠️  Warning: Custom module {mod_path_str} not found!")

    # Copy installed custom modules (e.g., editable installs)
    installed_modules = config.get('installed_modules', [])
    if installed_modules:
        print("📦 Copying installed custom modules from environment...")
        for mod_name in installed_modules:
            spec = importlib.util.find_spec(mod_name)
            if spec is None:
                print(f"⚠️  Warning: Installed module '{mod_name}' not found in the current Python environment!")
                continue
            
            if spec.submodule_search_locations:
                # It's a package (directory)
                mod_path = Path(spec.submodule_search_locations[0])
                dest_path = build_dir / mod_name
                shutil.copytree(mod_path, dest_path, dirs_exist_ok=True)
                print(f"   - Added installed package: {mod_name}")
            elif spec.origin:
                # It's a single file module
                mod_path = Path(spec.origin)
                dest_path = build_dir / mod_path.name
                shutil.copy2(mod_path, dest_path)
                print(f"   - Added installed file: {mod_path.name}")

    # Remove unnecessary directories
    print("🧹 Cleaning up unnecessary files...")
    exclude_patterns = config.get('exclude_patterns', ['__pycache__', '*.pyc'])
    clean_unnecessary_files(build_dir, exclude_patterns)

    # Create pip.txt
    pip_file = build_dir / "pip.txt"
    print("📝 Generating pip.txt...")
    with open(pip_file, 'w') as f:
        for pkg in config.get('pip_packages', []):
            f.write(f"{pkg}\n")

    # Create ZIP archive
    zip_name = config['project_name']
    print(f"🤐 Zipping the build folder into {zip_name}.zip...")
    shutil.make_archive(zip_name, 'zip', build_dir)

    print("✅ Preparation complete!")

def cleanup_deployment(config_file: str, clean_zip: bool):
    """Executes Phase 3: Cleanup"""
    config = load_config(config_file)
    build_dir = Path(config['build_dir'])
    
    print(f"🧹 Starting cleanup for: {config['project_name']}")
    
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"   - Removed build directory: {build_dir}")
    else:
        print(f"   - Build directory {build_dir} not found. Skipping.")
        
    if clean_zip:
        zip_file = Path(f"{config['project_name']}.zip")
        if zip_file.exists():
            zip_file.unlink()
            print(f"   - Removed archive: {zip_file.name}")
            
    print("✅ Cleanup complete!")

def main():
    parser = argparse.ArgumentParser(description="WASDI Deployment Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Subparser for "prepare"
    prep_parser = subparsers.add_parser("prepare", help="Prepare the application for deployment")
    prep_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
    
    # Subparser for "cleanup"
    clean_parser = subparsers.add_parser("cleanup", help="Clean up build artifacts")
    clean_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
    clean_parser.add_argument("--clean-zip", action="store_true", help="Also delete the generated zip file")
    
    args = parser.parse_args()
    
    try:
        if args.command == "prepare":
            prepare_deployment(args.config)
        elif args.command == "cleanup":
            cleanup_deployment(args.config, args.clean_zip)
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()