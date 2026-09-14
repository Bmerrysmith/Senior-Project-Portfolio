#!/usr/bin/env python3
"""
FGCU Traffic System - Quick Start Launcher
Automatically starts both API server and web interface
"""

import subprocess
import threading
import time
import webbrowser
import sys
import os
from pathlib import Path

def print_banner():
    """Print system banner"""
    print("=" * 60)
    print("🚦 FGCU Traffic Management System - Clean Architecture")
    print("=" * 60)
    print("🤖 AI-Powered Traffic Monitoring & Forecasting")
    print("🌐 3D Cesium Visualization with Real Road Data")
    print("📊 FastAPI Backend with Machine Learning Models")
    print("=" * 60)

def check_dependencies():
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    try:
        import fastapi
        import sklearn
        import numpy
        import pandas
        print("✅ Python dependencies installed")
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Run: pip install -r requirements.txt")
        return False
    
    return True

def start_api_server():
    """Start the FastAPI server in background"""
    print("🚀 Starting API server...")
    
    api_dir = Path(__file__).parent / "api"
    os.chdir(api_dir)
    
    try:
        # Start uvicorn server
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "main:app", 
            "--host", "127.0.0.1",
            "--port", "8000",
            "--log-level", "info"
        ], check=True)
    except subprocess.CalledProcessError:
        print("❌ Failed to start API server")
        return False
    except KeyboardInterrupt:
        print("\n🛑 API server stopped")
        return True

def start_web_server():
    """Start the web server in background"""
    print("🌐 Starting web server...")
    
    web_dir = Path(__file__).parent / "web"
    os.chdir(web_dir)
    
    try:
        # Start HTTP server
        subprocess.run([
            sys.executable, "-m", "http.server", "8080"
        ], check=True)
    except subprocess.CalledProcessError:
        print("❌ Failed to start web server")
        return False
    except KeyboardInterrupt:
        print("\n🛑 Web server stopped")
        return True

def wait_for_server(url, timeout=30):
    """Wait for server to be ready"""
    import requests
    
    for i in range(timeout):
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
        print(f"⏳ Waiting for server... ({i+1}/{timeout})")
    
    return False

def main():
    """Main startup function"""
    print_banner()
    
    # Check dependencies
    if not check_dependencies():
        return
    
    print("\n🎯 Starting FGCU Traffic System...")
    print("📍 Location: FGCU Campus, Fort Myers, FL")
    print("🔗 Integrations: Cesium.js, OpenStreetMap, FastAPI")
    
    # Create threads for servers
    print("\n" + "=" * 40)
    print("🚀 LAUNCHING SERVICES")
    print("=" * 40)
    
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    web_thread = threading.Thread(target=start_web_server, daemon=True) 
    
    # Start API server
    api_thread.start()
    
    # Wait a bit for API to start
    print("⏳ Initializing API server...")
    time.sleep(3)
    
    # Check if API is ready
    if wait_for_server("http://127.0.0.1:8000/health", timeout=10):
        print("✅ API server ready at http://127.0.0.1:8000")
    else:
        print("⚠️  API server may not be ready")
    
    # Start web server
    web_thread.start()
    
    # Wait a bit for web server
    print("⏳ Initializing web server...")
    time.sleep(2)
    
    print("✅ Web server ready at http://127.0.0.1:8080")
    
    # Show system info
    print("\n" + "=" * 40)
    print("📊 SYSTEM READY")
    print("=" * 40)
    print("🌐 Main Dashboard: http://127.0.0.1:8080/")
    print("🚦 Traffic Viewer: http://127.0.0.1:8080/traffic-viewer.html") 
    print("🔧 API Endpoints: http://127.0.0.1:8000/")
    print("📋 API Docs: http://127.0.0.1:8000/docs")
    print("💚 Health Check: http://127.0.0.1:8000/health")
    
    # Open browser
    time.sleep(2)
    print("\n🌐 Opening browser...")
    webbrowser.open("http://127.0.0.1:8080/")
    
    try:
        print("\n" + "=" * 40)
        print("✨ FGCU Traffic System is now running!")
        print("=" * 40)
        print("📱 Features:")
        print("   • Real-time traffic monitoring")
        print("   • AI-powered forecasting")
        print("   • 3D Cesium visualization") 
        print("   • Interactive road network")
        print("   • Live traffic updates")
        print("\n🛑 Press Ctrl+C to stop all services")
        print("=" * 40)
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down FGCU Traffic System...")
        print("👋 Thank you for using our traffic management system!")
        print("=" * 60)

if __name__ == "__main__":
    main()