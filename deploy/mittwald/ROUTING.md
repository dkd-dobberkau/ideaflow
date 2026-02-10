# Mittwald Ingress / Domain Routing

Alle Services laufen im selben Mittwald-Projekt (`p-d49y5m`).

## Container-IDs

| Service | Short-ID | UUID | Ports |
|---------|----------|------|-------|
| garage | c-t1jqqw | 3d6e44bc-396d-4ea2-9faa-68daf61587eb | 3900/tcp, 3902/tcp |
| admin | c-g7kz6e | 2af579b4-0da5-4a04-9c99-76dbc33b361d | 8000/tcp |
| strfry | c-hjtg79 | aa416fc6-27c2-47bd-8424-758d36a7ac57 | 7777/tcp |

## Domain-Routing

| Domain | Ziel-Container | Port | Zweck |
|--------|---------------|------|-------|
| `publiqhub.com` | garage | 3902/tcp | Static Hosting (S3 Web) |
| `admin.publiqhub.com` | admin | 8000/tcp | Admin-Interface |
| `p-d49y5m.project.space` | garage | 3902/tcp | Static Hosting (Mittwald-Domain) |
| `www.publiqhub.com` | - | - | Redirect auf `https://publiqhub.com/` |

## Routen wiederherstellen

Falls Routen verloren gehen (z.B. durch `mw stack deploy` ohne alle Services):

```bash
# publiqhub.com -> garage web
mw domain virtualhost create \
  --hostname publiqhub.com \
  --path-to-container /:3d6e44bc-396d-4ea2-9faa-68daf61587eb:3902/tcp

# admin.publiqhub.com -> admin
mw domain virtualhost create \
  --hostname admin.publiqhub.com \
  --path-to-container /:2af579b4-0da5-4a04-9c99-76dbc33b361d:8000/tcp

# project.space -> garage web (System-Domain, kann nicht geloescht werden)
# Update via API:
curl -X PUT "https://api.mittwald.de/v2/ingresses/<INGRESS-ID>/paths" \
  -H "Authorization: Bearer $MITTWALD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"path": "/", "target": {"container": {"id": "3d6e44bc-396d-4ea2-9faa-68daf61587eb", "portProtocol": "3902/tcp"}}}]'
```

## Hinweise

- `mw stack deploy` (PUT) ersetzt den gesamten Stack. Services die nicht in der
  Compose-Datei stehen werden **geloescht**, und deren Ingress-Routen gehen verloren.
- Die `docker-compose.yml` fuer Mittwald muss daher **immer alle Services** enthalten.
- Container-UUIDs aendern sich bei Stack-Neuanlage. Nach Neuanlage muessen die
  Ingress-Routen mit den neuen UUIDs aktualisiert werden.
- Die `p-d49y5m.project.space` Domain kann nicht geloescht werden (System-Domain),
  nur per API aktualisiert werden.
