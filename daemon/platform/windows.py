"""
Windows-specific platform functionality.
Handles registry operations for native messaging host registration.
"""

import logging

logger = logging.getLogger(__name__)


def register_native_host(manifest_path):
    """
    Register native messaging host in Windows registry.
    This is a stub for the MVP - actual registration will be done via PowerShell script.
    """
    logger.info("Windows registry registration should be done via install script")
    pass


def unregister_native_host():
    """Remove native messaging host from Windows registry."""
    logger.info("Windows registry unregistration should be done via uninstall script")
    pass
