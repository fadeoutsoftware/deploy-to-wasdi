# Deploy to WASDI Tool

A Python utility to simplify and standardize the deployment preparation and cleanup phases for WASDI applications.

## Installation

For local development and usage, install it in editable mode from the root directory of this repository:

`pip install -e .`


## Usage

This tool reads a deploy_config.yaml file in your application's directory.

### Prepare Deployment

Creates the build directory, copies modules, strips unnecessary files, and generates the ZIP archive:

`deploy-to-wasdi prepare -c deploy_config.yaml`

### Deploy

Uploads the prepared archive as a new WASDI processor:

`deploy-to-wasdi deploy -c deploy_config.yaml`

### Update

Updates the archive files for an existing WASDI processor. If no matching processor exists, the command creates one:

`deploy-to-wasdi update -c deploy_config.yaml`

### Update Parameters

Updates the parameter sample configured through `params_file` or `params_sample`:

`deploy-to-wasdi params -c deploy_config.yaml`

### Cleanup

Removes the build directory created during preparation:

`deploy-to-wasdi cleanup -c deploy_config.yaml`

Cleanup behavior is configured in `deploy_config.yaml`: set `keep_zip: true` to retain the archive, or `remove_build_dir: true` to remove the build directory when the archive is not being retained.
