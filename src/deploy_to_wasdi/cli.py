import os
import sys
import shutil
import yaml
import json
import argparse
import importlib.util
import urllib.parse
from pathlib import Path
from datetime import datetime

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
    
    # We ensure the build directory exists and overwrite files instead of wiping it,
    # which avoids issues with file locks and allows incremental updates.
    if not build_dir.exists():
        build_dir.mkdir(parents=True, exist_ok=True)
        
    print(f"📂 Copying/updating source code from {source_dir} to {build_dir}...")
    shutil.copytree(source_dir, build_dir, dirs_exist_ok=True)
    
    # Verify and Rename entry point
    entry_config = config.get('entry_point')
    if entry_config:
        entry_source = build_dir / entry_config['source']
        entry_target = build_dir / entry_config['target']
        
        if not entry_source.exists():
            print(f"❌ Error: Main entry point '{entry_config['source']}' not found in source directory.")
            sys.exit(1)
            
        if entry_source != entry_target:
            # Use replace instead of rename to ensure it safely overwrites if entry_target already exists
            entry_source.replace(entry_target)
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


_WASDI_INITIALIZED = False
_DEPLOYED_PROCESSORS_CACHE = None

def init_wasdi(config: dict, config_dir: Path):
    """Initializes the WASDI session, ensuring it only happens once per script execution."""
    global _WASDI_INITIALIZED
    if _WASDI_INITIALIZED:
        return
        
    import wasdi

    wasdi_config = config.get('wasdi_config', 'local_data/config.json')
    wasdi_config_path = Path(wasdi_config) if Path(wasdi_config).is_absolute() else config_dir / wasdi_config
    
    if not wasdi_config_path.exists():
        print(f"⚠️  Warning: WASDI config file not found at {wasdi_config_path}. wasdi.init() might prompt for credentials interactively.")
    
    print(f"🔑 Initializing WASDI...")
    try:
        wasdi.init(str(wasdi_config_path))
        _WASDI_INITIALIZED = True
    except Exception as e:
        print(f"❌ Error obtaining WASDI session: {e}")
        sys.exit(1)


def get_workspace_id(config: dict, config_dir: Path, wasdi_module) -> str:
    """Attempts to robustly retrieve the active workspace ID."""
    wid = config.get('workspace_id')
    if wid:
        return wid
        
    # Attempt to pull the active workspace from the initialized wasdi module
    try:
        wid = wasdi_module.getActiveWorkspaceId()
        if wid:
            return wid
    except AttributeError:
        pass
        
    # Fallback to reading the wasdi config file directly
    wasdi_config = config.get('wasdi_config', 'local_data/config.json')
    wasdi_config_path = Path(wasdi_config) if Path(wasdi_config).is_absolute() else config_dir / wasdi_config
    if wasdi_config_path.exists():
        try:
            with open(wasdi_config_path, 'r') as f:
                c = json.load(f)
                return c.get('workspaceId') or c.get('workspace') or c.get('workspace_id') or ''
        except Exception:
            pass
            
    return ''

def get_processor_info(config_file: str) -> dict:
    """
    Fetches the processor information from WASDI.
    Caches the list of deployed processors to ensure the REST endpoint is hit only once.
    """
    global _DEPLOYED_PROCESSORS_CACHE

    print(f'Trying to retrieve processor information from WASDI API for config: {config_file}...')
    
    try:
        import requests
        import wasdi
    except ImportError:
        return None

    config = load_config(config_file)
    config_dir = Path(config_file).resolve().parent
    project_name = config['project_name']
    
    init_wasdi(config, config_dir)
    
    if _DEPLOYED_PROCESSORS_CACHE is None:
        try:
            workspace_id = get_workspace_id(config, config_dir, wasdi)
            base_url = wasdi.getBaseUrl().rstrip('/')
            session_id = wasdi.getSessionId()
        except Exception as e:
            print(f"❌ Error retrieving WASDI session variables: {e}")
            return None
            
        headers = {'x-session-token': session_id}
        get_url = f"{base_url}/processors/getdeployed"
        
        try:
            res = requests.get(get_url, headers=headers, params={'workspace': workspace_id})
            if res.status_code == 200:
                _DEPLOYED_PROCESSORS_CACHE = res.json()
            else:
                print(f"⚠️ Could not fetch processors list (Status {res.status_code} at {get_url}).")
                _DEPLOYED_PROCESSORS_CACHE = []
        except Exception as e:
            print(f"⚠️ Failed to retrieve processor_id automatically: {e}")
            _DEPLOYED_PROCESSORS_CACHE = []

    # Find the specific processor
    for p in _DEPLOYED_PROCESSORS_CACHE:
        if p.get('name') == project_name or p.get('processorName') == project_name:
            return p
            
    return None

def deploy_to_wasdi(config_file: str):
    """Executes Phase 2: Deploy to WASDI (New Processor)"""
    try:
        import requests
        import wasdi
    except ImportError as e:
        print(f"❌ Error: Missing required library for deployment ({e.name}).")
        print(f"   Please install it using: pip install {e.name}")
        sys.exit(1)

    config = load_config(config_file)
    config_dir = Path(config_file).resolve().parent
    
    build_dir = Path(config['build_dir'])
    project_name = config['project_name']
    zip_name = f"{project_name}.zip"
    zip_path = build_dir / zip_name
    
    if not zip_path.exists():
        print(f"❌ Error: Deployment archive not found at {zip_path}")
        print("   Did you run 'prepare' first?")
        sys.exit(1)
        
    print(f"🚀 Starting deployment to WASDI for: {project_name}")
    
    init_wasdi(config, config_dir)
    
    try:
        workspace_id = get_workspace_id(config, config_dir, wasdi)
        if not workspace_id:
            print("❌ Error: Workspace ID is missing. Please define 'workspace_id' in deploy_config.yaml.")
            sys.exit(1)
            
        # Rely cleanly on the waspy environment state
        base_url = wasdi.getBaseUrl().rstrip('/')
        session_id = wasdi.getSessionId()
    except Exception as e:
        print(f"❌ Error retrieving WASDI session variables: {e}")
        sys.exit(1)
        
    endpoint = f"{base_url}/processors/uploadprocessor"
    headers = {'x-session-token': session_id}
    
    params_sample = config.get('params_sample')
    params_file = config.get('params_file', 'local_data/params.json')
    params_file_path = Path(params_file) if Path(params_file).is_absolute() else config_dir / params_file
    
    if params_file_path.exists():
        print(f"📄 Loading params_sample from {params_file_path.name}...")
        try:
            with open(params_file_path, 'r') as pf:
                # Parse and minify to remove spaces and newlines to shrink URL size
                params_obj = json.load(pf)
                params_sample = json.dumps(params_obj, separators=(',', ':'))
        except json.JSONDecodeError:
            print("⚠️  Warning: params_sample is not valid JSON. Sending as raw string.")
            with open(params_file_path, 'r') as pf:
                params_sample = pf.read().strip()
    elif params_sample is None:
        params_sample = '{}'
    elif isinstance(params_sample, dict):
        params_sample = json.dumps(params_sample, separators=(',', ':'))
    elif isinstance(params_sample, str):
        try:
            params_sample = json.dumps(json.loads(params_sample), separators=(',', ':'))
        except json.JSONDecodeError:
            params_sample = params_sample.strip()
    
    # Force integer mapping for public flag
    is_public_int = int("1" if config.get('public', 0) in [1, True, "true", "True", "1"] else "0")

    # WASDI API explicitly relies on @QueryParam for all metadata.
    # We pass this cleanly to `params=`, while the ZIP file is delivered via `files=`
    query_params = {
        'workspace': str(workspace_id),
        'name': str(project_name),
        'description': str(config.get('description', f'{project_name} Processor')),
        'public': is_public_int
    }

    proc_type = config.get('processor_type', None)
    if proc_type:
        query_params['type'] = str(proc_type)
    else:
        query_params['type'] = 'pip_oneshot'

    timeout = config.get('timeout')
    if (isinstance(timeout, str) and timeout.isdigit()) or isinstance(timeout, int):
        query_params['timeout'] = int(timeout)

    print(f"query_params prepared for deployment (before adding paramsSample): {query_params}")

    # Let requests handle the URL encoding automatically. 
    # Manual urllib.parse.quote causes double-encoding, exponentially inflating the URL length.
    query_params['paramsSample'] = str(params_sample)

    print(f"📡 Uploading new processor {zip_name} to {endpoint}...")
    
    try:
        with open(zip_path, 'rb') as f:
            files = {'file': (zip_name, f, 'application/zip')}
            # Send metadata in the URL (params), binary file in the body (files)
            response = requests.post(endpoint, headers=headers, params=query_params, files=files)
            
        if response.status_code == 200:
            print("✅ Deployment successful!")
            try:
                result = response.json()
                print(f"   Server Response: {result}")
            except Exception:
                print(f"   Server Response: {response.text}")
        else:
            print(f"❌ Deployment failed with status {response.status_code}")
            print(f"   Server Response: {response.text}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Network error during deployment: {e}")
        sys.exit(1)


def update_to_wasdi(config_file: str):
    """Executes Phase 2.5: Update existing processor on WASDI"""
    try:
        import requests
        import wasdi
    except ImportError as e:
        print(f"❌ Error: Missing required library for update ({e.name}).")
        sys.exit(1)

    config = load_config(config_file)
    config_dir = Path(config_file).resolve().parent
    
    build_dir = Path(config['build_dir'])
    project_name = config['project_name']
    zip_name = f"{project_name}.zip"
    zip_path = build_dir / zip_name
    
    if not zip_path.exists():
        print(f"❌ Error: Update archive not found at {zip_path}")
        print("   Did you run 'prepare' first?")
        sys.exit(1)
        
    print(f"🚀 Starting code update to WASDI for existing processor: {project_name}")
    
    try:
        workspace_id = get_workspace_id(config, config_dir, wasdi)
        base_url = wasdi.getBaseUrl().rstrip('/')
        session_id = wasdi.getSessionId()
    except Exception as e:
        print(f"❌ Error retrieving WASDI session variables: {e}")
        sys.exit(1)
        
    endpoint = f"{base_url}/processors/updatefiles"
    headers = {'x-session-token': session_id}
    
    print(f"🔍 Attempting to retrieve processor_id for '{project_name}' from WASDI API ({base_url})...")
    processor_info = get_processor_info(config_file)
        
    if not processor_info:
        print(f"⚠️  Could not find an existing processor named '{project_name}'.")
        print("   Falling back to 'deploy' to create a new processor...")
        deploy_to_wasdi(config_file)
        return
    
    processor_id = processor_info.get('processorId')
    print(f"✅ Resolved processor_id: {processor_id}")

    # Send metadata to the URL query string (@QueryParam), just like deployment
    query_params = {
        'workspace': str(workspace_id),
        'processorId': str(processor_id),
        'name': str(project_name),
        'file': str(zip_name)
    }

    print(f"📡 Updating {zip_name} files at {endpoint}...")
    
    try:
        with open(zip_path, 'rb') as f:
            files = {'file': (zip_name, f, 'application/zip')}
            response = requests.post(endpoint, headers=headers, params=query_params, files=files)
            
        if response.status_code == 200:
            print("✅ Update successful!")
            try:
                result = response.json()
                print(f"   Server Response: {result}")
            except Exception:
                print(f"   Server Response: {response.text}")
        else:
            print(f"❌ Update failed with status {response.status_code}")
            print(f"   Server Response: {response.text}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Network error during update: {e}")
        sys.exit(1)


def update_params(config_file: str):
    """Executes Phase 2.6: Update parameters sample of an existing processor via HTTP POST body"""
    try:
        import requests
        import wasdi
    except ImportError as e:
        print(f"❌ Error: Missing required library ({e.name}).")
        sys.exit(1)

    config = load_config(config_file)
    config_dir = Path(config_file).resolve().parent
    project_name = config['project_name']
    
    print(f"🚀 Starting params update to WASDI for existing processor: {project_name}")
    
    try:
        workspace_id = get_workspace_id(config, config_dir, wasdi)
        base_url = wasdi.getBaseUrl().rstrip('/')
        session_id = wasdi.getSessionId()
    except Exception as e:
        print(f"❌ Error retrieving WASDI session variables: {e}")
        sys.exit(1)
        
    headers = {'x-session-token': session_id, 'Content-Type': 'application/json'}
    
    print(f"🔍 Fetching existing processor details for '{project_name}' from WASDI API ({base_url})...")
    processor_view_model = get_processor_info(config_file)
        
    if not processor_view_model:
        print(f"❌ Error: Could not find an existing processor named '{project_name}'. Please deploy it first.")
        sys.exit(1)
    
    print(f"✅ Found existing processor_id: {processor_view_model.get('processorId')}")

    # Prepare paramsSample (Since it goes in the JSON body, we don't need to minify it)
    params_sample = config.get('params_sample')
    params_file = config.get('params_file', 'local_data/params.json')
    params_file_path = Path(params_file) if Path(params_file).is_absolute() else config_dir / params_file
    
    if params_file_path.exists():
        print(f"📄 Loading params_sample from {params_file_path.name}...")
        with open(params_file_path, 'r') as pf:
            params_sample = pf.read().strip()
    elif params_sample is None:
        params_sample = '{}'
    elif isinstance(params_sample, dict):
        print(f'params_sample provided as dict in config, converting to JSON string...')
        params_sample = json.dumps(params_sample, indent=2)

    print(f"   - Loaded params_sample: {params_sample[:300]}{'...' if len(params_sample) > 300 else ''}")
        
    # Update the retrieved view model dictionary
    processor_view_model['paramsSample'] = str(params_sample)

    # We also update timeout if provided
    timeout = config.get('timeout')
    if (isinstance(timeout, str) and timeout.isdigit()) or isinstance(timeout, int):
        processor_view_model['minuteTimeout'] = int(timeout)
        
    update_url = f"{base_url}/processors/update"
    print(f"📡 Sending updated DeployedProcessorViewModel to {update_url}...")
    
    query_params = {
        'processorId': str(processor_view_model.get('processorId'))
    }
    try:
        # Pass the dictionary directly to json=, requests handles JSON encoding automatically
        response = requests.post(update_url, params=query_params, headers=headers, json=processor_view_model)
        
        if response.status_code == 200:
            print("✅ Parameters update successful!")
        else:
            print(f"❌ Parameters update failed with status {response.status_code}")
            print(f"   Server Response: {response.text}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Network error during params update: {e}")
        sys.exit(1)


def cleanup_deployment(config_file: str):
    """Executes Phase 3: Cleanup"""
    config = load_config(config_file)
    build_dir = Path(config['build_dir'])
    zip_name = f"{config['project_name']}.zip"
    
    keep_zip = config.get('keep_zip', False)
    remove_build_dir = config.get('remove_build_dir', False)
    
    print(f"🧹 Starting cleanup for: {config['project_name']}")
    
    if build_dir.exists():
        if remove_build_dir and not keep_zip:
            shutil.rmtree(build_dir)
            print(f"   - Removed entire build directory: {build_dir}")
        else:
            if remove_build_dir and keep_zip:
                print(f"   ⚠️ Warning: 'remove_build_dir' is True but 'keep_zip' is also True. Preserving build directory to keep the zip file.")
            
            for item in build_dir.iterdir():
                if keep_zip and item.name == zip_name:
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            
            kept_msg = f" but kept {zip_name}" if keep_zip else ""
            print(f"   - Cleaned contents of {build_dir}{kept_msg}")
    else:
        print(f"   - Build directory {build_dir} not found. Skipping.")
            
    print("✅ Cleanup complete!")

def main():
    start_time = datetime.now()
    print(f"🕒 Execution started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("🚀 Welcome to the WASDI Deployment Utility! v.1.0")
    
    try:
        parser = argparse.ArgumentParser(description="WASDI Deployment Utility")
        parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
        subparsers = parser.add_subparsers(dest="command", required=False)
        
        prep_parser = subparsers.add_parser("prepare", help="Prepare the application for deployment")
        prep_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
        
        deploy_parser = subparsers.add_parser("deploy", help="Deploy the prepared zip file to WASDI as a new processor")
        deploy_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
        
        update_parser = subparsers.add_parser("update", help="Update the files of an existing processor on WASDI")
        update_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
        
        update_params_parser = subparsers.add_parser("params", help="Update the parameters sample of an existing processor via HTTP POST body")
        update_params_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
        
        clean_parser = subparsers.add_parser("cleanup", help="Clean up build artifacts")
        clean_parser.add_argument("-c", "--config", default="deploy_config.yaml", help="Path to YAML config file")
        
        args = parser.parse_args()
        
        if args.command is None:
            print("🔄 No command provided. Executing adaptive deployment pipeline...")
            cleanup_deployment(args.config)
            prepare_deployment(args.config)
            
            print("\n🔍 Checking if processor is already deployed on WASDI...")
            processor_info = get_processor_info(args.config)
            
            if processor_info:
                print(f"✅ Processor '{processor_info.get('processorName', processor_info.get('name'))}' already exists.")
                print("   Proceeding to update parameters and code...")
                # update_params(args.config)
                update_to_wasdi(args.config)
            else:
                print("🆕 Processor not found on WASDI. Proceeding to deploy as a new processor...")
                deploy_to_wasdi(args.config)
                
        elif args.command == "prepare":
            prepare_deployment(args.config)
        elif args.command == "deploy":
            deploy_to_wasdi(args.config)
        elif args.command == "update":
            update_to_wasdi(args.config)
        elif args.command == "params":
            update_params(args.config)
        elif args.command == "cleanup":
            cleanup_deployment(args.config)

    finally:
        end_time = datetime.now()
        print(f"\n🏁 Execution finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⏱️ Total duration: {end_time - start_time}")

if __name__ == "__main__":
    main()