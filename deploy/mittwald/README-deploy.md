# strfry Nostr Relay - Mittwald Deployment

## Voraussetzungen

- Mittwald vServer mit Container-Hosting (ab vServer S)
- [Mittwald CLI](https://developer.mittwald.de/docs/v2/cli/) installiert (`brew install mittwald/tap/mw`)
- GitHub Account mit Zugriff auf `ghcr.io/dkd-dobberkau`

## Automatisches Deployment (GitHub Actions)

Push auf `main` löst automatisch Build + Deploy aus, wenn sich diese Dateien ändern:
- `strfry.conf`
- `deploy/mittwald/Dockerfile.strfry`
- `deploy/mittwald/docker-compose.yml`

Manuell auslösbar via "Run workflow" im Actions-Tab.

### Einmalige Einrichtung

#### 1. Mittwald API Token erstellen

Im mStudio Dashboard unter "API Tokens" einen neuen Token erstellen.

#### 2. GitHub Secrets & Variables konfigurieren

Im GitHub Repo unter Settings > Secrets and variables > Actions:

**Secrets:**
- `MITTWALD_API_TOKEN` - API Token aus Schritt 1

**Variables:**
- `MITTWALD_STACK_ID` - Stack-UUID (siehe Schritt 4)

#### 3. Mittwald CLI einrichten

```bash
# CLI installieren (macOS)
brew install mittwald/tap/mw

# Einloggen
mw login

# Projekt-Kontext setzen
mw context set --project-id=<PROJECT-ID>
```

#### 4. Stack-ID ermitteln

```bash
# Erstes Deployment manuell anstoßen, um den Stack zu erzeugen
mw stack deploy --compose-file=deploy/mittwald/docker-compose.yml

# Stack-ID anzeigen
mw container list
```

Die Stack-ID als `MITTWALD_STACK_ID` Variable in GitHub hinterlegen.

#### 5. GHCR Registry bei Mittwald registrieren

Falls das GitHub-Repo privat ist:

```bash
mw registry create \
  --uri ghcr.io \
  --username <GITHUB-USER> \
  --password <GITHUB-TOKEN> \
  -p <PROJECT-ID>
```

#### 6. Domain/Ingress einrichten

```bash
# Container-UID aus der Liste holen
mw container list

# Domain mappen
mw domain virtualhost create \
  --hostname relay.euredomain.de \
  --path-to-container /:<CONTAINER-UID>:7777/tcp
```

Danach ist das Relay erreichbar unter: `wss://relay.euredomain.de`

## Relay testen

```bash
# Lokal per Port-Forward testen
mw container port-forward <CONTAINER-ID> 7777

# Oder mit wscat (npm install -g wscat)
wscat -c wss://relay.euredomain.de
> ["REQ","test",{"limit":1}]
```

## Logs & Debugging

```bash
# Container-Status
mw container list

# Logs anzeigen
mw container logs <CONTAINER-ID>

# In den Container verbinden
mw container ssh <CONTAINER-ID>
```

## Hinweise

- **Architektur**: Das Image wird als `linux/amd64` gebaut (Mittwald unterstützt kein ARM)
- **Image-Tags**: Jedes Deployment nutzt den Git-SHA als Tag + `latest`
- **Daten**: Die strfry-Datenbank liegt im Stack-Volume `strfry-data` und wird automatisch per Mittwald-Backup gesichert
- **WebSocket**: WSS läuft über den HTTPS-Ingress von Mittwald (HTTP Upgrade). Falls WSS nicht funktioniert: Mittwald-Support kontaktieren
- **Ressourcen**: 512 MB RAM und 1 CPU reichen für ein Relay mit moderater Last
