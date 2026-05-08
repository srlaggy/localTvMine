import base64
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import re
from urllib.parse import urljoin

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

PROXY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://tvtvhd.com/",
}

@router.get("/{path:path}")
async def proxy_media(url: str, request: Request, path: str = ""):
    try:
        # Añadir padding en caso de que falte por el envío en la URL
        padded_url = url + '=' * (-len(url) % 4)
        target_url = base64.b64decode(padded_url).decode('utf-8')
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    client = httpx.AsyncClient(headers=PROXY_HEADERS, follow_redirects=True, timeout=15.0)
    req = client.build_request("GET", target_url)
    
    try:
        r = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Error fetching from upstream: {str(e)}")

    if r.status_code != 200:
        await r.aclose()
        await client.aclose()
        raise HTTPException(status_code=r.status_code, detail=f"Upstream returned status {r.status_code}")

    content_type = r.headers.get("content-type", "")

    # Si es una playlist m3u8, la leemos, reescribimos los enlaces internos y la retornamos como texto
    if "mpegurl" in content_type.lower() or target_url.endswith(".m3u8") or ".m3u8?" in target_url:
        content = await r.aread()
        await r.aclose()
        await client.aclose()
        
        text = content.decode('utf-8', errors='ignore')
        new_lines = []
        
        def replacer(match):
            uri = match.group(1)
            abs_url = urljoin(target_url, uri)
            encoded_url = base64.b64encode(abs_url.encode('utf-8')).decode('utf-8')
            return f'URI="{request.url.scheme}://{request.url.netloc}/api/proxy/stream.m3u8?url={encoded_url}"'

        for line in text.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                new_lines.append(line)
                continue
                
            if line_stripped.startswith("#"):
                if 'URI="' in line_stripped:
                    line_stripped = re.sub(r'URI="([^"]+)"', replacer, line_stripped)
                new_lines.append(line_stripped)
            else:
                abs_url = urljoin(target_url, line_stripped)
                encoded_url = base64.b64encode(abs_url.encode('utf-8')).decode('utf-8')
                proxy_url = f"{request.url.scheme}://{request.url.netloc}/api/proxy/stream.m3u8?url={encoded_url}"
                new_lines.append(proxy_url)
        
        return Response(content="\n".join(new_lines), media_type="application/vnd.apple.mpegurl")

    # Para fragmentos de video u otros archivos binarios, los transmitimos por streaming
    async def stream_gen():
        try:
            async for chunk in r.aiter_bytes(chunk_size=8192):
                yield chunk
        finally:
            await r.aclose()
            await client.aclose()

    return StreamingResponse(stream_gen(), media_type=content_type)
