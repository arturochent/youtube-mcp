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

# Paths — use absolute path to ensure Claude Desktop finds the files
# regardless of what working directory it launches the server from
BASE_DIR = Path(r"C:\youtube-mcp")
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
            part="snippet,contentDetails,status",
            mine=True,
            maxResults=max_results,
        ).execute()

        playlists = []
        for item in response.get("items", []):
            playlists.append({
                "playlist_id": item["id"],
                "title": item["snippet"]["title"],
                "video_count": item["contentDetails"]["itemCount"],
                "privacy": item["status"]["privacyStatus"],
                "url": f"https://www.youtube.com/playlist?list={item['id']}",
            })

        return json.dumps({"playlists": playlists, "total": len(playlists)}, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def get_playlist_items(playlist_id: str, max_results: int = 50) -> str:
    """Get all videos inside a playlist."""
    youtube = get_youtube_client()

    try:
        items = []
        next_page_token = None

        while True:
            kwargs = dict(
                part="snippet",
                playlistId=playlist_id,
                maxResults=min(max_results, 50),
            )
            if next_page_token:
                kwargs["pageToken"] = next_page_token

            response = youtube.playlistItems().list(**kwargs).execute()

            for item in response.get("items", []):
                snippet = item["snippet"]
                resource = snippet.get("resourceId", {})
                items.append({
                    "position": snippet.get("position", 0) + 1,
                    "video_id": resource.get("videoId", ""),
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("videoOwnerChannelTitle", ""),
                    "url": f"https://www.youtube.com/watch?v={resource.get('videoId', '')}",
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token or len(items) >= max_results:
                break

        return json.dumps({
            "playlist_id": playlist_id,
            "total": len(items),
            "items": items,
        }, indent=2)

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
        current = youtube.playlists().list(
            part="snippet,status",
            id=playlist_id,
        ).execute()

        if not current.get("items"):
            return json.dumps({"error": "Playlist not found."})

        item = current["items"][0]
        snippet = item["snippet"]
        status = item["status"]

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
# NEW TOOLS
# ---------------------------------------------------------------------------

def remove_video_from_playlist(playlist_id: str, video_id: str) -> str:
    """Remove a specific video from a playlist."""
    youtube = get_youtube_client()

    try:
        # Find the playlistItem ID for this video
        response = youtube.playlistItems().list(
            part="id",
            playlistId=playlist_id,
            videoId=video_id,
        ).execute()

        items = response.get("items", [])
        if not items:
            return json.dumps({"error": "Video not found in this playlist."})

        playlist_item_id = items[0]["id"]

        youtube.playlistItems().delete(id=playlist_item_id).execute()

        return json.dumps({
            "success": True,
            "removed_video_id": video_id,
            "playlist_id": playlist_id,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def delete_playlist(playlist_id: str) -> str:
    """Permanently delete a YouTube playlist."""
    youtube = get_youtube_client()

    try:
        youtube.playlists().delete(id=playlist_id).execute()

        return json.dumps({
            "success": True,
            "deleted_playlist_id": playlist_id,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def get_video_details(video_id: str) -> str:
    """Get detailed info about a video: title, description, duration, views, likes."""
    youtube = get_youtube_client()

    try:
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=video_id,
        ).execute()

        items = response.get("items", [])
        if not items:
            return json.dumps({"error": "Video not found."})

        item = items[0]
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        details = item.get("contentDetails", {})

        return json.dumps({
            "video_id": video_id,
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "channel_id": snippet["channelId"],
            "description": snippet.get("description", "")[:500],
            "published_at": snippet.get("publishedAt", ""),
            "duration": details.get("duration", ""),  # ISO 8601 e.g. PT4M13S
            "view_count": stats.get("viewCount", "N/A"),
            "like_count": stats.get("likeCount", "N/A"),
            "comment_count": stats.get("commentCount", "N/A"),
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def get_channel_info(channel_id: str) -> str:
    """Get info about a YouTube channel: name, description, subscriber count, video count."""
    youtube = get_youtube_client()

    try:
        response = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=channel_id,
        ).execute()

        items = response.get("items", [])
        if not items:
            return json.dumps({"error": "Channel not found."})

        item = items[0]
        snippet = item["snippet"]
        stats = item.get("statistics", {})

        return json.dumps({
            "channel_id": channel_id,
            "name": snippet["title"],
            "description": snippet.get("description", "")[:500],
            "country": snippet.get("country", "N/A"),
            "published_at": snippet.get("publishedAt", ""),
            "subscriber_count": stats.get("subscriberCount", "hidden"),
            "video_count": stats.get("videoCount", "N/A"),
            "view_count": stats.get("viewCount", "N/A"),
            "url": f"https://www.youtube.com/channel/{channel_id}",
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": str(e)})


def get_my_subscriptions(max_results: int = 25) -> str:
    """List the channels the authenticated user is subscribed to."""
    youtube = get_youtube_client()

    try:
        subscriptions = []
        next_page_token = None

        while len(subscriptions) < max_results:
            kwargs = dict(
                part="snippet",
                mine=True,
                maxResults=min(50, max_results - len(subscriptions)),
                order="alphabetical",
            )
            if next_page_token:
                kwargs["pageToken"] = next_page_token

            response = youtube.subscriptions().list(**kwargs).execute()

            for item in response.get("items", []):
                snippet = item["snippet"]
                channel_id = snippet["resourceId"]["channelId"]
                subscriptions.append({
                    "channel_id": channel_id,
                    "name": snippet["title"],
                    "description": snippet.get("description", "")[:200],
                    "url": f"https://www.youtube.com/channel/{channel_id}",
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return json.dumps({
            "total": len(subscriptions),
            "subscriptions": subscriptions,
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
        Tool(
            name="get_playlist_items",
            description="Get all videos inside a playlist by playlist ID. Returns track list with titles, channels and URLs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string", "description": "The playlist ID to inspect"},
                    "max_results": {"type": "integer", "description": "Max videos to return (default 50)", "default": 50},
                },
                "required": ["playlist_id"],
            },
        ),
        # ---- NEW TOOLS ----
        Tool(
            name="remove_video_from_playlist",
            description="Remove a specific video from a playlist by video ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string", "description": "The playlist ID"},
                    "video_id": {"type": "string", "description": "The video ID to remove"},
                },
                "required": ["playlist_id", "video_id"],
            },
        ),
        Tool(
            name="delete_playlist",
            description="Permanently delete a YouTube playlist by playlist ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string", "description": "The playlist ID to delete"},
                },
                "required": ["playlist_id"],
            },
        ),
        Tool(
            name="get_video_details",
            description=(
                "Get detailed info about a YouTube video: title, channel, "
                "duration, view count, like count, comment count, and more."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "video_id": {"type": "string", "description": "The YouTube video ID"},
                },
                "required": ["video_id"],
            },
        ),
        Tool(
            name="get_channel_info",
            description=(
                "Get info about a YouTube channel: name, description, "
                "subscriber count, video count, total views, and more."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "The YouTube channel ID"},
                },
                "required": ["channel_id"],
            },
        ),
        Tool(
            name="get_my_subscriptions",
            description="List all channels the authenticated user is subscribed to.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Max subscriptions to return (default 25)", "default": 25},
                },
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
        elif name == "get_playlist_items":
            result = get_playlist_items(**arguments)
        # ---- NEW TOOLS ----
        elif name == "remove_video_from_playlist":
            result = remove_video_from_playlist(**arguments)
        elif name == "delete_playlist":
            result = delete_playlist(**arguments)
        elif name == "get_video_details":
            result = get_video_details(**arguments)
        elif name == "get_channel_info":
            result = get_channel_info(**arguments)
        elif name == "get_my_subscriptions":
            result = get_my_subscriptions(**arguments)
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
