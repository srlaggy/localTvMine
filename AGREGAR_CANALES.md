# Cómo agregar canales a localTv

## Opción 1 — Importar desde lista M3U (recomendado)

Sirve para agregar canales en bloque desde fuentes como iptv-org o m3u.cl.

### Con Docker (producción)

```bash
# Primero reconstruir si hay cambios en el código
docker compose build backend

# Importar canales (el script corre dentro del contenedor con acceso a la BD)
docker compose run --rm backend python3 scripts/import_m3u.py https://iptv-org.github.io/iptv/countries/cl.m3u
```

### Sin Docker (local/desarrollo)

```bash
cd backend
python3 scripts/import_m3u.py https://iptv-org.github.io/iptv/countries/cl.m3u
```

### Opciones del script

```bash
# Ver canales que se importarían sin guardar nada
python3 scripts/import_m3u.py <url> --dry-run

# Forzar todos los canales a una categoría específica
python3 scripts/import_m3u.py <url> --category nacional

# Importar desde archivo local
python3 scripts/import_m3u.py /ruta/lista.m3u
```

El script:
- Ignora duplicados (por slug y por URL)
- Crea categorías automáticamente desde el `group-title` del M3U
- Limpia nombres: quita resolución `(1080p)`, flags `[Not 24/7]`, etc.

### Fuentes M3U conocidas

| Fuente | URL | Contenido |
|---|---|---|
| iptv-org Chile | `https://iptv-org.github.io/iptv/countries/cl.m3u` | ~86 canales nacionales y regionales |
| iptv-org Argentina | `https://iptv-org.github.io/iptv/countries/ar.m3u` | Canales argentinos |
| iptv-org (todo) | `https://iptv-org.github.io/iptv/index.m3u` | 10.000+ canales internacionales |
| m3u.cl regionales | `https://m3u.cl/regionales.php` | Regionales chilenos |

---

## Opción 2 — Canal suelto via API REST

Para agregar un canal manualmente, primero necesitas el `category_id`.

```bash
# Ver categorías disponibles
curl http://localhost:8000/api/categories/

# Agregar canal (stream_url puede ser URL .m3u8 directa o tvtvhd.com)
curl -X POST http://localhost:8000/api/channels/ \
  -H "X-API-Key: bustatv-dev-secret-key-changeme" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ChileVisión",
    "slug": "chilevision",
    "stream_url": "http://38.250.127.17:9800/play/a05h/index.m3u8",
    "logo_url": "https://i.imgur.com/PRijvR0.png",
    "category_id": 1,
    "is_active": true
  }'
```

---

## Cómo funciona el streaming

El backend soporta dos tipos de `stream_url`:

| Tipo | Ejemplo | Comportamiento |
|---|---|---|
| URL `.m3u8` directa | `https://servidor.cl/canal/playlist.m3u8` | Se retorna tal cual al player |
| URL tvtvhd.com | `https://tvtvhd.com/vivo/canales.php?stream=espn` | El backend hace scraping para extraer la URL real |

---

## Dónde vive la base de datos

En Docker, la BD SQLite se persiste en el volumen `bustav_db` montado en `/app/data/bustaTv.db` dentro del contenedor. No se borra al reiniciar ni al hacer `docker compose down`. Solo se borra con:

```bash
docker compose down -v   # ⚠️ borra la BD completa
```
