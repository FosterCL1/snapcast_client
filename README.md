# Snapcast Client

A Buildroot-based and updatable client for Snapcast and Raspberry Pi based speakers.

## What is Snapcast?

[Snapcast](https://github.com/badaix/snapcast) is a multi-room audio streaming system that provides perfectly synchronized audio playback across multiple devices.
It integrates seamlessly with [Home Assistant](https://www.home-assistant.io/integrations/snapcast/) and other audio sources, enabling whole-home audio without the need for proprietary hardware or vendor lock-in.

## Project Purpose

While there are many guides for setting up a Snapcast client on a Raspberry Pi, most involve manual OS installation and Snapclient setup, which complicates maintenance and updates.

This project simplifies the process by providing:

- **Easy Updates**: Streamlined system updates with rollback capability
- **Development Flexibility**: Support for experimental builds and testing
- **Extensibility**: Simple addition of new features and packages
- **Reliability**: Robust update mechanism with automatic rollback on failure

## Core Technologies

### Buildroot

[Buildroot](https://buildroot.org/) is a powerful tool for generating embedded Linux systems. It provides:
- Cross-compilation toolchain
- Package management
- Custom root filesystem generation
- Kernel and bootloader configuration

### RAUC

[RAUC (Robust Auto-Update Controller)](https://rauc.io/) is a safe and secure software update framework for embedded Linux. Key features include:
- Atomic updates with A/B partitioning
- Automatic rollback on update failure
- Integrity verification of update packages
- Support for full system updates

### Hawkbit

[Eclipse Hawkbit™](https://eclipse.dev/hawkbit/) is a domain-independent back-end framework for managing software updates to constrained edge devices. It provides:
- Over-the-Air (OTA) update management
- Device grouping and targeting
- Rollout management
- Integration with RAUC via the [RAUC Hawkbit Updater](https://github.com/rauc/rauc-hawkbit-updater)
- Web-based administration interface
With this, it is possible to perform a central location to manage the whole house (or larger) deployment.

### BR2Rauc

The [BR2Rauc Project](https://github.com/cdsteinkuehler/br2rauc) offered the framework to get this project off the ground.
Without it, this project would not exist.

### Home Assistant

[Home Assistant](https://www.home-assistant.io/) and the addon [Music Assistant](https://www.music-assistant.io/) offer the front end to the project.
If the front end weren't robust and usable, nothing else would matter.

## Hawkbit Server Setup

A local Hawkbit server is needed.
To achieve this, the following site has instructions:

```
https://test-microplatform-docs.readthedocs.io/en/stable/fota-demo/device-mgmt/hawkbit_local.html
```

The UI should be accessible via the IP address, port 8080, with user/password
admin/admin.
