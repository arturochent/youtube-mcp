#!/usr/bin/env python3
"""
YouTube MCP Server
Allows Claude to search YouTube channels/artists and manage playlists
via the YouTube Data API v3 with OAuth2 authentication.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Scopes required for YouTube read + write access
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# Paths (relative to this file)
BASE_DIR = Path(__file__).parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "token.json"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_youtube_client():
    """Authenticate and return a YouTube API client."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"client_secret.json not found at {CLIENT_SECRET_FILE}. "
                    "Please download it from Google Cloud Console and place it "
                    "in the same folder as server.py."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_artists(
    query: str,
    max_results: int = 10,
    genre: str | None = None,
) -> str:
    """Search YouTube for artist channels matching a query and optional genre."""
    youtube = get_youtube_client()

    search_query = query
    if genre:
        search_query = f"{query} {genre} music"

    try:
        response = youtube.search().list(
            q=search_query,
            part="snippet",
            type="channel",
            maxResults=max_results,
        ).execute()

        results = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            channel_id = item["id"]["channelId"]
            results.append({
                "channel_id": channel_id,
                "name": snippet["title"],
                "description": snippet.get("description", "")[:200],
                "url": f"https://www.youtube.com/channel/{channel_id}",
            })

        if not results:
            return json.dumps({"message": "No artist channels found.", "results": []})

        return json.dumps({"results": results, "total_found": len(results)}, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def search_videos(
    query: str,
    max_results: int = 25,
    genre: str | None = None,
    channel_id: str | None = None,
) -> str:
    """Search YouTube for videos matching a query."""
    youtube = get_youtube_client()

    search_query = query
    if genre:
        search_query = f"{query} {genre}"

    try:
        kwargs: dict[str, Any] = dict(
            q=search_query,
            part="snippet",
            type="video",
            maxResults=max_results,
            videoCategoryId="10",  # Music category
        )
        if channel_id:
            kwargs["channelId"] = channel_id

        response = youtube.search().list(**kwargs).execute()

        results = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            video_id = item["id"]["videoId"]
            results.append({
                "video_id": video_id,
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                "description": snippet.get("description", "")[:150],
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })

        return json.dumps({"results": results, "total_found": len(results)}, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def create_playlist(
    title: str,
    description: str = "",
    privacy: str = "private",
) -> str:
    """Create a new YouTube playlist on the authenticated account."""
    youtube = get_youtube_client()

    try:
        response = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": privacy},
            },
        ).execute()

        playlist_id = response["id"]
        return json.dumps({
            "success": True,
            "playlist_id": playlist_id,
            "title": response["snippet"]["title"],
            "url": f"https://www.youtube.com/playlist?list={playlist_id}",
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def add_videos_to_playlist(playlist_id: str, video_ids: list[str]) -> str:
    """Add a list of video IDs to an existing playlist."""
    youtube = get_youtube_client()

    added = []
    errors = []

    for video_id in video_ids:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
            added.append(video_id)
        except HttpError as e:
            errors.append({"video_id": video_id, "error": str(e)})

    return json.dumps({
        "added_count": len(added),
        "added_video_ids": added,
        "errors": errors,
        "playlist_url": f"https://www.youtube.com/playlist?list={playlist_id}",
    }, indent=2)


def list_my_playlists(max_results: int = 25) -> str:
    """List the authenticated user's playlists."""
    youtube = get_youtube_client()

    try:
        response = youtube.playlists().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=max_results,
        ).execute()

        playlists = []
        for item in response.get("items", []):
            playlists.append({
                "playlist_id": item["id"],
                "title": item["snippet"]["title"],
                "video_count": item["contentDetails"]["itemCount"],
                "url": f"https://www.youtube.com/playlist?list={item['id']}",
            })

        return json.dumps({"playlists": playlists, "total": len(playlists)}, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def update_playlist(
    playlist_id: str,
    title: str | None = None,
    description: str | None = None,
    privacy: str | None = None,
) -> str:
    """Update a playlist's title, description, or privacy setting."""
    youtube = get_youtube_client()

    try:
        # Fetch current playlist data first
        current = youtube.playlists().list(
            part="snippet,status",
            id=playlist_id,
        ).execute()

        if not current.get("items"):
            return json.dumps({"error": "Playlist not found."})

        item = current["items"][0]
        snippet = item["snippet"]
        status = item["status"]

        # Apply updates
        updated_snippet = {
            "title": title if title is not None else snippet["title"],
            "description": description if description is not None else snippet.get("description", ""),
        }
        updated_status = {
            "privacyStatus": privacy if privacy is not None else status["privacyStatus"],
        }

        response = youtube.playlists().update(
            part="snippet,status",
            body={
                "id": playlist_id,
                "snippet": updated_snippet,
                "status": updated_status,
            },
        ).execute()

        return json.dumps({
            "success": True,
            "playlist_id": playlist_id,
            "title": response["snippet"]["title"],
            "privacy": response["status"]["privacyStatus"],
            "url": f"https://www.youtube.com/playlist?list={playlist_id}",
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

app = Server("youtube-playlist-manager")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_artists",
            description=(
                "Search YouTube for artist/musician channels by name and optional genre. "
                "Returns channel IDs, names, and URLs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Artist name or keywords to search for"},
                    "genre": {"type": "string", "description": "Optional music genre to narrow the search (e.g. 'jazz', 'hip hop')"},
                    "max_results": {"type": "integer", "description": "Max channels to return (default 10, max 50)", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_videos",
            description=(
                "Search YouTube for music videos matching a query. "
                "Optionally filter by genre or restrict to a specific channel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms (artist name, song title, etc.)"},
                    "genre": {"type": "string", "description": "Optional genre filter"},
                    "channel_id": {"type": "string", "description": "Optional YouTube channel ID to search within"},
                    "max_results": {"type": "integer", "description": "Max videos to return (default 25, max 50)", "default": 25},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="create_playlist",
            description="Create a new YouTube playlist on the authenticated user's account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Playlist title"},
                    "description": {"type": "string", "description": "Optional playlist description"},
                    "privacy": {
                        "type": "string",
                        "enum": ["private", "public", "unlisted"],
                        "description": "Privacy setting (default: private)",
                        "default": "private",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="add_videos_to_playlist",
            description="Add one or more videos (by video ID) to an existing YouTube playlist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string", "description": "The playlist ID to add videos to"},
                    "video_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of YouTube video IDs to add",
                    },
                },
                "required": ["playlist_id", "video_ids"],
            },
        ),
        Tool(
            name="list_my_playlists",
            description="List all playlists on the authenticated user's YouTube account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Max playlists to return (default 25)", "default": 25},
                },
            },
        ),
        Tool(
            name="update_playlist",
            description="Update a playlist's title, description, or privacy setting (private, public, unlisted).",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string", "description": "The playlist ID to update"},
                    "title": {"type": "string", "description": "New title (optional)"},
                    "description": {"type": "string", "description": "New description (optional)"},
                    "privacy": {
                        "type": "string",
                        "enum": ["private", "public", "unlisted"],
                        "description": "New privacy setting (optional)",
                    },
                },
                "required": ["playlist_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "search_artists":
            result = search_artists(**arguments)
        elif name == "search_videos":
            result = search_videos(**arguments)
        elif name == "create_playlist":
            result = create_playlist(**arguments)
        elif name == "add_videos_to_playlist":
            result = add_videos_to_playlist(**arguments)
        elif name == "list_my_playlists":
            result = list_my_playlists(**arguments)
        elif name == "update_playlist":
            result = update_playlist(**arguments)
        else:
            result = json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        result = json.dumps({"error": str(e)})

    return [TextContent(type="text", text=result)]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
