import os
import sys
import shutil
import yaml
import argparse
import importlib.util
from pathlib import Path

def load_config(config_path: str) -> dict:
    """Loads the YAML configuration file."""
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"❌ Error: Configuration file not found: {config_path}")
        sys.exit(1)
        
    with open(config_file, 'r') as file:
        return yaml.safe_load(file)

def clean_unnecessary_files(target_dir: Path, exclude_patterns: list):
    """Removes files and directories matching the exclude patterns."""
    for pattern in exclude_patterns:
        for path in list(target_dir.rglob(pattern)):
            if not path.exists():
                continue
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
    
    # Check if source directory exists
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"❌ Error: Source directory '{source_dir}' does not exist.")
        sys.exit(1)
    
    if build_dir.exists():
        shutil.rmtree(build_dir)
        
    print(f"📂 Copying source code from {source_dir} to {build_dir}...")
    shutil.copytree(source_dir, build_dir)
    
    # Verify and Rename entry point
    entry_config = config.get('entry_point')
    if entry_config:
        entry_source = build_dir / entry_config['source']
        entry_target = build_dir / entry_config['target']
        
        if not entry_source.exists():
            print(f"❌ Error: Main entry point '{entry_config['source']}' not found in source directory.")
            sys.exit(1)
            
        if entry_source != entry_target:
            entry_source.rename(entry_target)
            print(f"🔄 Renamed {entry_source.name} to {entry_target.name}")
        else:
            print(f"✅ Main entry point verified: {entry_target.name}")

    # Copy custom local modules
    custom_modules = config.get('custom_modules')
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
    installed_modules = config.get('installed_modules')
    if installed_modules:
        print("📦 Copying installed custom modules from environment...")
        for mod_name in installed_modules:
            spec = importlib.util.find_spec(mod_name)
            if spec is None:
                print(f"⚠️  Warning: Installed module '{mod_name}' not found in the current Python environment!")
                continue
            
            if spec.submodule_search_locations:
                mod_path = Path(spec.submodule_search_locations[0])
                dest_path = build_dir / mod_name
                shutil.copytree(mod_path, dest_path, dirs_exist_ok=True)
                print(f"   - Added installed package: {mod_name}")
            elif spec.origin:
                mod_path = Path(spec.origin)
                dest_path = build_dir / mod_path.name
                shutil.copy2(mod_path, dest_path)
                print(f"   - Added installed file: {mod_path.name}")

    # Remove unnecessary directories
    print("🧹 Cleaning up unnecessary files...")
    exclude_patterns = config.get('exclude_patterns', ['__pycache__', '*.pyc'])
    clean_unnecessary_files(build_dir, exclude_patterns)

    # Create pip.txt
    pip_packages = config.get('pip_packages')
    if pip_packages:
        pip_file = build_dir / "pip.txt"
        print("📝 Generating pip.txt...")
        with open(pip_file, 'w') as f:
            for pkg in pip_packages:
                f.write(f"{pkg}\n")

    # Create ZIP archive safely
    zip_base_name = config['project_name']
    temp_zip_file = Path(f"{zip_base_name}.zip")
    
    print(f"🤐 Zipping the build folder...")
    # Generate zip in the root directory first to avoid recursive zipping issues
    shutil.make_archive(zip_base_name, 'zip', build_dir)
    
    # Move the zip file inside the build directory
    final_zip_path = build_dir / temp_zip_file.name
    if final_zip_path.exists():
        final_zip_path.unlink() # Delete if it already exists from a previous bad run
    shutil.move(str(temp_zip_file), str(final_zip_path))
    
    print(f"✅ Preparation complete! Your deployment file is ready at: {final_zip_path}")

def cleanup_deployment(config_file: str, clean_zip: bool):
    """Executes Phase 3: Cleanup"""
    config = load_config(config_file)
    build_dir = Path(config['build_dir'])
    zip_name = f"{config['project_name']}.zip"
    
    print(f"🧹 Starting cleanup for: {config['project_name']}")
    
    if build_dir.exists():
        if clean_zip:
            # Delete the entire directory including the zip
            shutil.rmtree(build_dir)
            print(f"   - Removed entire build directory: {build_dir}")
        else:
            # Delete everything inside EXCEPT the zip file
            for item in build_dir.iterdir():
                if item.name != zip_name:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
            print(f"   - Cleaned build artifacts but kept: {build_dir / zip_name}")
    else:
        print(f"   - Build directory {build_dir} not found. Skipping.")
            
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
    
    if args.command == "prepare":
        prepare_deployment(args.config)
    elif args.command == "cleanup":
        cleanup_deployment(args.config, args.clean_zip)

if __name__ == "__main__":
    main()