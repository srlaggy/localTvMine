#!/usr/bin/env python3
"""
Importa canales desde una lista M3U a la base de datos de localTv.

Uso (desde el directorio backend/):
  python scripts/import_m3u.py <url_o_archivo>
  python scripts/import_m3u.py https://iptv-org.github.io/iptv/countries/cl.m3u
  python scripts/import_m3u.py mi_lista.m3u --dry-run
  python scripts/import_m3u.py mi_lista.m3u --category nacional
"""

import sys
import re
import argparse
import unicodedata
from pathlib import Path

# Agregar el directorio raíz del backend al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from app.database import SessionLocal, engine, Base
from app.models.channel import Channel
from app.models.category import Category

Base.metadata.create_all(bind=engine)


# Mapa de group-title (M3U) → (nombre español, slug, icono FontAwesome)
GROUP_TO_CATEGORY = {
    "general":       ("Nacional",        "nacional",        "fa-tv"),
    "culture":       ("Cultura",         "cultura",         "fa-landmark"),
    "entertainment": ("Entretenimiento", "entretenimiento", "fa-star"),
    "music":         ("Música",          "musica",          "fa-music"),
    "news":          ("Noticias",        "noticias",        "fa-newspaper"),
    "kids":          ("Infantil",        "infantil",        "fa-child"),
    "comedy":        ("Comedia",         "comedia",         "fa-laugh"),
    "series":        ("Series",          "series",          "fa-film"),
    "documentary":   ("Documentales",    "documentales",    "fa-book"),
    "lifestyle":     ("Lifestyle",       "lifestyle",       "fa-heart"),
    "religious":     ("Religioso",       "religioso",       "fa-cross"),
    "legislative":   ("Gobierno",        "gobierno",        "fa-landmark"),
    "sports":        ("Deportes",        "deportes",        "fa-futbol"),
    "travel":        ("Viajes",          "viajes",          "fa-globe"),
    "undefined":     ("Sin categoría",   "sin-categoria",   "fa-question"),
}


def slugify(text: str) -> str:
    """Genera slug desde un nombre: minúsculas, sin acentos, guiones."""
    # Quitar resolución entre paréntesis: "(1080p)", "(720p)", "(SD)"
    text = re.sub(r"\s*\([^)]*(?:p|P|i|I|SD|HD)\)", "", text).strip()
    # Quitar flags entre corchetes: "[Not 24/7]"
    text = re.sub(r"\s*\[[^\]]*\]", "", text).strip()
    # Normalizar unicode y quitar diacríticos
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Minúsculas y reemplazar no-alfanuméricos por guión
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def clean_name(text: str) -> str:
    """Limpia el nombre del canal quitando info de resolución."""
    text = re.sub(r"\s*\([^)]*(?:p|P|i|I|SD|HD)\)", "", text).strip()
    text = re.sub(r"\s*\[[^\]]*\]", "", text).strip()
    return text


def parse_m3u(content: str) -> list[dict]:
    """Parsea contenido M3U y retorna lista de dicts con info de cada canal."""
    channels = []
    lines = content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line.startswith("#EXTINF"):
            i += 1
            continue

        extinf_line = line

        logo_match = re.search(r'tvg-logo="([^"]*)"', extinf_line)
        logo = logo_match.group(1) if logo_match else None

        group_match = re.search(r'group-title="([^"]*)"', extinf_line)
        group = group_match.group(1) if group_match else "Undefined"

        # Nombre: texto después de la última coma de la línea EXTINF
        name_match = re.search(r",([^,\n]+)$", extinf_line)
        name = name_match.group(1).strip() if name_match else None

        if not name:
            i += 1
            continue

        # Avanzar hasta encontrar la URL (saltando líneas #EXTVLCOPT u otras)
        i += 1
        url = None
        while i < len(lines):
            next_line = lines[i].strip()
            if next_line and not next_line.startswith("#"):
                url = next_line
                break
            i += 1

        if url and (url.startswith("http://") or url.startswith("https://")):
            channels.append({
                "name": name,
                "logo": logo or "",
                "group": group,
                "url": url,
            })

        i += 1

    return channels


def get_or_create_category(db, group_title: str) -> Category:
    """Obtiene o crea una categoría a partir del group-title del M3U."""
    key = group_title.lower().strip()
    cat_name, cat_slug, cat_icon = GROUP_TO_CATEGORY.get(
        key, (group_title, slugify(group_title) or "otros", "fa-tv")
    )

    cat = db.query(Category).filter(Category.slug == cat_slug).first()
    if not cat:
        cat = Category(name=cat_name, slug=cat_slug, icon=cat_icon)
        db.add(cat)
        db.flush()

    return cat


def import_m3u(source: str, dry_run: bool = False, category_slug: str = None):
    """
    Importa canales desde una URL o archivo M3U local.

    Args:
        source: URL https:// o ruta local al archivo .m3u
        dry_run: Si True, solo muestra los canales sin escribir en BD
        category_slug: Si se especifica, fuerza todos los canales a esa categoría
    """
    # Leer contenido
    if source.startswith("http://") or source.startswith("https://"):
        print(f"Descargando M3U desde {source} ...")
        try:
            response = httpx.get(source, timeout=30, follow_redirects=True)
            response.raise_for_status()
            content = response.text
        except httpx.HTTPError as e:
            print(f"Error descargando M3U: {e}")
            sys.exit(1)
    else:
        path = Path(source)
        if not path.exists():
            print(f"Archivo no encontrado: {source}")
            sys.exit(1)
        print(f"Leyendo archivo {source} ...")
        content = path.read_text(encoding="utf-8")

    channels = parse_m3u(content)
    print(f"Canales encontrados en el M3U: {len(channels)}\n")

    if dry_run:
        for ch in channels:
            print(f"  [{ch['group']:15}] {ch['name'][:40]:40} → {ch['url']}")
        print(f"\nTotal: {len(channels)} canales (dry-run, nada fue guardado)")
        return

    db = SessionLocal()
    try:
        added = 0
        skipped = 0

        # Si se forzó una categoría específica, verificar que existe
        forced_category = None
        if category_slug:
            forced_category = db.query(Category).filter(Category.slug == category_slug).first()
            if not forced_category:
                print(f"Categoría '{category_slug}' no encontrada en la BD.")
                print("Categorías disponibles:")
                for cat in db.query(Category).all():
                    print(f"  - {cat.slug} ({cat.name})")
                sys.exit(1)

        for ch in channels:
            name = clean_name(ch["name"])
            slug = slugify(ch["name"])

            if not slug:
                print(f"  SKIP (slug vacío): {ch['name']}")
                skipped += 1
                continue

            # Verificar duplicado por slug
            if db.query(Channel).filter(Channel.slug == slug).first():
                print(f"  SKIP (slug duplicado): {name} [{slug}]")
                skipped += 1
                continue

            # Verificar duplicado por URL
            if db.query(Channel).filter(Channel.stream_url == ch["url"]).first():
                print(f"  SKIP (URL duplicada):  {name}")
                skipped += 1
                continue

            # Obtener categoría
            cat = forced_category if forced_category else get_or_create_category(db, ch["group"])

            channel = Channel(
                name=name or ch["name"],
                slug=slug,
                stream_url=ch["url"],
                logo_url=ch["logo"] if ch["logo"] else None,
                category_id=cat.id,
                is_active=True,
            )
            db.add(channel)
            added += 1
            print(f"  ADD: {name[:40]:40} [{slug}] → {cat.name}")

        db.commit()
        print(f"\n✓ Importación completada: {added} agregados, {skipped} omitidos")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Error durante importación: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Importar canales desde una lista M3U a localTv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/import_m3u.py https://iptv-org.github.io/iptv/countries/cl.m3u
  python scripts/import_m3u.py mi_lista.m3u --dry-run
  python scripts/import_m3u.py mi_lista.m3u --category nacional
        """
    )
    parser.add_argument("source", help="URL o ruta al archivo .m3u")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostrar canales sin guardar en BD")
    parser.add_argument("--category", metavar="SLUG",
                        help="Forzar todos los canales a esta categoría (slug)")
    args = parser.parse_args()

    import_m3u(args.source, dry_run=args.dry_run, category_slug=args.category)
