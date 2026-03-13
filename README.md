# YouTube MCP Server — Setup Guide

A Python MCP server that lets Claude search YouTube for artists and manage playlists on your account.

---

## Prerequisites

- Python 3.11 or newer
- A Google account with YouTube

---

## Step 1 — Get Google API credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services → Library**
4. Search for **YouTube Data API v3** and click **Enable**
5. Go to **APIs & Services → Credentials**
6. Click **+ Create Credentials → OAuth client ID**
7. Application type: **Desktop app** → give it a name → click **Create**
8. Click **Download JSON** — save the file as `client_secret.json` in this folder

---

## Step 2 — Install dependencies

Open a terminal in this folder and run:

```bash
pip install -r requirements.txt
```

---

## Step 3 — Configure Claude Desktop

Open your Claude Desktop config file:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the following entry inside the `"mcpServers"` object (create the object if it doesn't exist):

```json
{
  "mcpServers": {
    "youtube-playlist-manager": {
      "command": "python",
      "args": ["/FULL/PATH/TO/THIS/FOLDER/server.py"]
    }
  }
}
```

Replace `/FULL/PATH/TO/THIS/FOLDER/` with the actual path where you saved these files.

**Example on Mac:**
```json
{
  "mcpServers": {
    "youtube-playlist-manager": {
      "command": "python3",
      "args": ["/Users/yourname/youtube_mcp/server.py"]
    }
  }
}
```

---

## Step 4 — First run (OAuth flow)

1. **Restart Claude Desktop** after saving the config
2. The first time you use a YouTube tool, a browser window will open asking you to sign in with Google and grant access
3. After approval, a `token.json` file is saved locally — you won't need to log in again

---

## Available Tools

| Tool | Description |
|------|-------------|
| `search_artists` | Search for artist/musician channels by name + optional genre |
| `search_videos` | Search for music videos, optionally within a specific channel |
| `create_playlist` | Create a new playlist on your YouTube account |
| `add_videos_to_playlist` | Add videos (by ID) to an existing playlist |
| `list_my_playlists` | List all your YouTube playlists |

---

## Example prompts to try in Claude

- *"Search for jazz guitar artists on YouTube and create a playlist of their top videos"*
- *"Find lo-fi hip hop channels and make a private playlist called 'Focus Music'"*
- *"Search for videos by artist name 'Khruangbin' and add them to my existing playlist"*
- *"List all my YouTube playlists"*

---

## Files in this folder

```
youtube_mcp/
├── server.py           ← The MCP server (main file)
├── requirements.txt    ← Python dependencies
├── client_secret.json  ← YOU ADD THIS (downloaded from Google Cloud)
├── token.json          ← Auto-created after first login
└── README.md           ← This file
```

---

## Troubleshooting

**"client_secret.json not found"** → Make sure you downloaded and renamed the file correctly and placed it in the same folder as `server.py`.

**"Access blocked" in browser** → Your OAuth app may be in "testing" mode. Go to Google Cloud Console → OAuth consent screen → Add your Google account as a test user.

**Tool not appearing in Claude** → Double-check the path in `claude_desktop_config.json` and restart Claude Desktop fully.
