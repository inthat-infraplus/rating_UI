# Deployment Helpers

This folder contains reverse-proxy helpers for exposing the app with an internal hostname instead of a raw IP.

## Recommended on Windows: IIS

Files:

- `deployment/iis/enable_iis_prereqs.ps1`
- `deployment/iis/web.config`
- `deployment/iis/setup_iis_proxy.ps1`
- `deployment/iis/add_hosts_entry.ps1`

Suggested hostname:

- `rating-ui.infra.local`

Backend app:

- `http://127.0.0.1:8081`

Run:

```powershell
.\deployment\iis\enable_iis_prereqs.ps1
.\deployment\iis\setup_iis_proxy.ps1 -HostName "rating-ui.infra.local" -FrontendPort 80
```

Optional local hosts entry helper:

```powershell
.\deployment\iis\add_hosts_entry.ps1 -HostName "rating-ui.infra.local" -ServerIp "192.168.120.231"
```

Notes:

- Install `IIS URL Rewrite`
- Install `Application Request Routing (ARR)`
- Map `rating-ui.infra.local` to `192.168.120.231` in internal DNS or client `hosts`

## Alternative: nginx

File:

- `deployment/nginx/rating-ui.conf`

Use it as a site/server block and update `server_name` if needed.
