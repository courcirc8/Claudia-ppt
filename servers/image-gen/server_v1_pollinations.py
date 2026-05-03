"""
Image Generation MCP Server
Uses Pollinations AI for free image generation without API keys
"""

import asyncio
import base64
from pathlib import Path
from typing import Any
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.server.stdio

# Initialize server
app = Server("image-gen")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available image generation tools."""
    return [
        Tool(
            name="generate_image",
            description="Generate an image from a text prompt using AI. Returns the image as base64.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The text description of the image to generate"
                    },
                    "width": {
                        "type": "integer",
                        "description": "Width of the generated image (default: 1024)",
                        "default": 1024
                    },
                    "height": {
                        "type": "integer",
                        "description": "Height of the generated image (default: 1024)",
                        "default": 1024
                    },
                    "model": {
                        "type": "string",
                        "description": "Model to use: 'flux' (default, high quality) or 'turbo' (faster)",
                        "default": "flux",
                        "enum": ["flux", "turbo"]
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional path to save the image (e.g., 'output.png')"
                    }
                },
                "required": ["prompt"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for image generation."""
    if name != "generate_image":
        raise ValueError(f"Unknown tool: {name}")
    
    prompt = arguments.get("prompt")
    width = arguments.get("width", 1024)
    height = arguments.get("height", 1024)
    model = arguments.get("model", "flux")
    save_path = arguments.get("save_path")
    
    if not prompt:
        raise ValueError("Prompt is required")
    
    # Generate image using Pollinations API
    # API endpoint: https://image.pollinations.ai/prompt/{prompt}
    # Parameters: width, height, model
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Construct URL with parameters
            url = f"https://image.pollinations.ai/prompt/{prompt}"
            params = {
                "width": width,
                "height": height,
                "model": model,
                "nologo": "true"
            }
            
            response = await client.get(url, params=params, follow_redirects=True)
            response.raise_for_status()
            
            # Get image data
            image_data = response.content
            
            # Convert to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Save if path provided
            if save_path:
                # BUG FIX (2026-03-31): CWE-22 path traversal — user-supplied save_path
                # could write files outside intended directory (e.g. ../../etc/cron.d/evil).
                # Fix: restrict writes to user home directory subtree only.
                safe_base = Path.home()
                save_file = (safe_base / Path(save_path).name).resolve()
                if not str(save_file).startswith(str(safe_base)):
                    raise ValueError(f"Save path outside allowed directory: {save_path}")
                save_file.parent.mkdir(parents=True, exist_ok=True)
                save_file.write_bytes(image_data)
                save_message = f"\n\nImage saved to: {save_file}"
            else:
                save_message = ""
            
            return [
                TextContent(
                    type="text",
                    text=f"✅ Image generated successfully for prompt: '{prompt}'\n"
                         f"Dimensions: {width}x{height}\n"
                         f"Model: {model}{save_message}"
                ),
                ImageContent(
                    type="image",
                    data=image_base64,
                    mimeType="image/png"
                )
            ]
    
    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to generate image: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Error generating image: {str(e)}")

async def main():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())



