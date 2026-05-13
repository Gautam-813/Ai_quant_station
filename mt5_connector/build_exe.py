
import PyInstaller.__main__
import os
import sys

def build():
    print("Building MT5 Connector Executable...")
    
    # Path to connector.py
    script_path = "connector.py"
    
    # PyInstaller arguments
    args = [
        script_path,
        "--onefile",             # Create a single EXE
        "--name=MT5_Connector",  # Name of the EXE
        "--console",             # Show console window
        "--clean",               # Clean cache
    ]
    
    try:
        PyInstaller.__main__.run(args)
        print("\nSUCCESS! Your EXE is in the 'dist' folder.")
        print("You can now run 'MT5_Connector.exe' on any Windows machine with MT5 installed.")
    except Exception as e:
        print(f"\nError building EXE: {e}")
        print("Make sure you have pyinstaller installed: pip install pyinstaller")

if __name__ == "__main__":
    build()
