# 🤖 Cline-X

**A powerful Flask-based API server that bridges Cline (Claude Dev) with multiple AI models, featuring a beautiful web control panel and smart notification system.**

## ✨ Features

### 🎯 Multi-Model Support
- **Gemini** - Google's powerful AI model
- **DeepSeek** - Advanced reasoning capabilities
- **AIStudio** - Creative AI interactions

Switch between models instantly through the web interface!

### 🎨 Beautiful Control Panel
- **Modern UI** with light/dark theme support
- **Real-time model switching** without restarts
- **Configurable notifications** and alerts
- **Remote access** via ngrok integration

### 📱 Smart Notifications
- **Push notifications** via ntfy.sh
- **Terminal alerts** with ASCII art for task completions
- **Summary extraction** for quick updates
- **Configurable levels**: None, Completions only, or All actions

### 🌐 Remote Access
- **ngrok integration** for secure remote access
- **API key authentication** for security
- Access Cline-X from anywhere in the world

### ⚙️ Flexible Configuration
- **Terminal output levels**: None, Minimal, Default, Debug
- **Alert customization**: Choose when to get notified
- **Persistent settings** saved across sessions
- **Easy setup** with web-based configuration

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Windows OS (for clipboard functionality)
- ngrok account (optional, for remote access)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/cline-x.git
   cd cline-x
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file in the project root:
   ```env
   NGROK_AUTHTOKEN=your_ngrok_token_here  # Optional
   ```

4. **Configure your AI model credentials**
   Add your API keys to the `.env` file or configure through the web interface

5. **Run the server**
   ```bash
   python main.py
   ```

6. **Open the control panel**
   Navigate to `http://127.0.0.1:3001` in your browser

### 📦 Using the Pre-built Executable

If you prefer not to set up Python, download the pre-built executable from the [Releases](../../releases) section. Simply extract and run `Cline-X.exe`!

## 📖 Usage

### Connecting to Cline

1. Start Cline-X server
2. In your Cline extension settings, point the API endpoint to:
   - Local: `http://127.0.0.1:3001/`
   - Remote: Use the ngrok URL shown in the control panel

### Control Panel Features

**🤖 AI Model Selection**
- Switch between Gemini, DeepSeek, and AIStudio with one click

**📋 Terminal Output Levels**
- **None**: Silent operation
- **Minimal**: Essential messages only
- **Default**: Standard logging
- **Debug**: Verbose output for troubleshooting

**🎯 Terminal Alerts**
- **None**: No visual alerts
- **Completions**: Alert when tasks complete
- **All + Summaries**: Real-time updates with AI-generated summaries

**📱 Push Notifications (ntfy.sh)**
- Get instant notifications on your phone
- One-click topic generation
- Configurable notification levels

**🌐 Remote Access**
- Enable/disable ngrok tunnel
- View public URL and API key
- Secure authentication

## 🔧 Configuration

Settings are stored in `clinex_config.json` (formerly `config.txt`) and persist across restarts:

```json
{
  "model": "gemini",
  "theme": "dark",
  "ntfy_topic": "",
  "ntfy_notification_level": "none",
  "terminal_log_level": "default",
  "terminal_alert_level": "none",
  "tunnel_active": "False",
  "auth_required": "False"
}
```

## 🎨 Terminal Alerts

When enabled, Cline-X displays beautiful ASCII art notifications in your terminal:

- **Completion alerts** with eye-catching borders
- **Summary displays** for AI actions
- **Auto-clearing** previous alerts for clean output

## 🔐 Security

- API key authentication for remote access
- Secure ngrok tunneling
- Rate limiting on requests (Default: 20 per minute for chat, 5 per minute for toggles)
- Environment-based credential storage
- CSRF Protection enabled

## 🛠️ Development

### Key Dependencies
- **Flask** & **Flask-WTF** - Web framework & Security
- **Flask-Limiter** - API Rate limiting
- **pyngrok** - ngrok integration for remote access
- **talktollm** - Multi-model AI interface
- **optimisewait** - Window focus & automation optimization
- **pyautogui** & **pygetwindow** - GUI automation
- **win32clipboard** - Windows clipboard access
- **Pillow** - Image processing
- **colorama** - Terminal colors
- **requests** - HTTP client
- **python-dotenv** - Environment management

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 💬 Support

Having issues? Open an issue on GitHub or check the [documentation](../../wiki).

## 🌟 Show Your Support

If you find Cline-X useful, please consider giving it a star on GitHub!

---

**Built with ❤️ for the Cline community**

