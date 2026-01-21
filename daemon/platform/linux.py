"""
Linux-specific platform functionality.
Handles native messaging host registration for Linux.
"""

import logging
import os
import json

logger = logging.getLogger(__name__)


def register_native_host(manifest_path):
    """
    Register native messaging host on Linux.
    Firefox on Linux looks for manifests in:
    ~/.mozilla/native-messaging-hosts/
    """
    target_dir = os.path.expanduser("~/.mozilla/native-messaging-hosts")
    os.makedirs(target_dir, exist_ok=True)
    
    manifest_name = os.path.basename(manifest_path)
    target_path = os.path.join(target_dir, manifest_name)
    
    logger.info(f"Symlinking {manifest_path} to {target_path}")
    
    if os.path.exists(target_path):
        os.remove(target_path)
    
    os.symlink(manifest_path, target_path)
    logger.info("Native host registered successfully")


def unregister_native_host(manifest_name="com.xavier.voice_browser.json"):
    """Remove native messaging host registration."""
    target_dir = os.path.expanduser("~/.mozilla/native-messaging-hosts")
    target_path = os.path.join(target_dir, manifest_name)
    
    if os.path.exists(target_path):
        os.remove(target_path)
        logger.info("Native host unregistered")
