import re
import base64
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.crud import channels as crud_channels

router = APIRouter(prefix="/api/streams", tags=["streams"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://tvtvhd.com/",
}

async def _scrape_tvtvhd(tvtvhd_url: str) -> str:
    """Extrae la URL real del stream desde una página de tvtvhd.com"""

    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS, follow_redirects=True) as client:
            response = await client.get(tvtvhd_url)
            html_content = response.text

        # Buscar playbackURL en el HTML - patrón más preciso
        match = re.search(r'playbackURL\s*[=:]\s*["\']?([^"\'<>]+\.m3u8[^"\'<>]*)["\']?', html_content)
        if match:
            url = match.group(1)
            if url.startswith('http'):
                return url

        # Buscar en etiqueta source
        match = re.search(r'<source[^>]+src=["\']([^"\']+\.m3u8[^"\']*)["\']', html_content)
        if match:
            return match.group(1)

        # Buscar en data-src o atributos similares
        match = re.search(r'data-src=["\']?([https://][^"\'<>]+\.m3u8[^"\'<>]*)["\']?', html_content)
        if match:
            return match.group(1)

        # Último intento: buscar cualquier URL que contenga m3u8
        match = re.search(r'(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)', html_content)
        if match:
            return match.group(1)

        raise ValueError("No se encontró la URL del stream")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extrayendo stream: {str(e)}")

@router.get("/{channel_slug}")
async def get_stream(channel_slug: str, request: Request, db: Session = Depends(get_db)):
    """Obtiene la URL del stream para un canal específico.

    - Si el canal tiene una URL .m3u8 directa (ej: IPTV), la retorna tal cual.
    - Si el canal apunta a tvtvhd.com, extrae el stream mediante scraping.
    """
    # Buscar canal en la BD
    channel = crud_channels.get_channel_by_slug(db, channel_slug)

    if channel and channel.stream_url:
        stream_url = channel.stream_url

        # URL directa: ya es un stream .m3u8, retornar sin scraping
        if ".m3u8" in stream_url:
            return {
                "url": stream_url,
                "channel": channel_slug,
                "headers": {}
            }

        # URL de tvtvhd: necesita scraping
        if "tvtvhd.com" in stream_url:
            try:
                resolved_url = await _scrape_tvtvhd(stream_url)
                encoded_url = base64.b64encode(resolved_url.encode('utf-8')).decode('utf-8')
                base_url_str = f"{request.url.scheme}://{request.url.netloc}/api/proxy/stream.m3u8?url="
                proxy_url = f"{base_url_str}{encoded_url}"
                return {
                    "url": proxy_url,
                    "channel": channel_slug,
                    "is_proxied": True,
                    "headers": {}
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error extrayendo stream: {str(e)}")

    # Fallback: canal no encontrado en BD, intentar tvtvhd por slug directamente
    try:
        tvtvhd_url = f"https://tvtvhd.com/vivo/canales.php?stream={channel_slug}"
        resolved_url = await _scrape_tvtvhd(tvtvhd_url)
        encoded_url = base64.b64encode(resolved_url.encode('utf-8')).decode('utf-8')
        base_url_str = f"{request.url.scheme}://{request.url.netloc}/api/proxy/stream.m3u8?url="
        proxy_url = f"{base_url_str}{encoded_url}"
        return {
            "url": proxy_url,
            "channel": channel_slug,
            "is_proxied": True,
            "headers": {}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Canal '{channel_slug}' no encontrado o sin stream disponible")
