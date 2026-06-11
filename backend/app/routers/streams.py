import re
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/streams", tags=["streams"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://tvtvhd.com/",
}

def _extract_m3u8(html_content: str) -> str | None:
    """Busca URL m3u8 en contenido HTML"""
    match = re.search(r'playbackURL\s*[=:]\s*["\']?([^"\'<>]+\.m3u8[^"\'<>]*)["\']?', html_content)
    if match:
        url = match.group(1)
        if url.startswith('http'):
            return url

    match = re.search(r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']', html_content)
    if match:
        return match.group(1)

    match = re.search(r'data-src=["\']?([https://][^"\'<>]+\.m3u8[^"\'<>]*)["\']?', html_content)
    if match:
        return match.group(1)

    match = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', html_content)
    if match:
        return match.group(1)

    return None

def _extract_iframe_src(html_content: str) -> str | None:
    """Extrae la URL del iframe si la página es un wrapper"""
    match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_content)
    if match:
        return match.group(1)
    return None


async def get_stream_url(channel_slug: str) -> str:
    """Extrae la URL real del stream desde tvtvhd.com"""
    tvtvhd_url = f"https://tvtvhd.com/vivo/canales.php?stream={channel_slug}"

    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            response = await client.get(tvtvhd_url)
            html_content = response.text

        url = _extract_m3u8(html_content)
        if url:
            return url

        iframe_src = _extract_iframe_src(html_content)
        if iframe_src:
            async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
                iframe_response = await client.get(iframe_src)
            url = _extract_m3u8(iframe_response.text)
            if url:
                return url

        raise ValueError("No se encontró la URL del stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extrayendo stream: {str(e)}")

@router.get("/{channel_slug}")
async def get_stream(channel_slug: str):
    """Obtiene la URL del stream para un canal específico"""
    try:
        stream_url = await get_stream_url(channel_slug)

        # Retornar URL con headers necesarios para reproducción
        return {
            "url": stream_url,
            "channel": channel_slug,
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://tvtvhd.com/"
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
