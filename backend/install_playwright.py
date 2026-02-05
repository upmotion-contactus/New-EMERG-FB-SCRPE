#!/usr/bin/env python3
"""Script to install Playwright browsers - run on deployment startup"""
import subprocess
import sys
import os

def install_browsers():
    """Install Playwright Chromium browser"""
    print("Installing Playwright Chromium browser...")
    
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'playwright', 'install', 'chromium'],
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode == 0:
            print("✅ Playwright Chromium installed successfully")
            return True
        else:
            print(f"❌ Installation failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = install_browsers()
    sys.exit(0 if success else 1)
