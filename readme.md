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

Sorry, unsupported at the moment. Will do. For the moment, just drag and drop that zip of yours

### Cleanup

Removes the build directory created during preparation:

`deploy-to-wasdi cleanup -c deploy_config.yaml`


To also delete the generated .zip file:

`deploy-to-wasdi cleanup -c deploy_config.yaml --clean-zip`
