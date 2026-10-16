$Base = "http://localhost:8000"

# 1) Pedir CSRF (crea la cookie de sesión anónima)
$r = Invoke-RestMethod -Uri "$Base/auth/csrf" -SessionVariable sess
$csrf = $r.csrf_token
Write-Host "== CSRF inicial: $csrf"

# 2) Login
$body = @{ username = "superadmin"; password = "Admin@1234" } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "$Base/auth/login" -Method Post `
    -WebSession $sess -ContentType "application/json" `
    -Headers @{ "X-CSRF-Token" = $csrf } -Body $body
Write-Host "== Login OK:"
$login | ConvertTo-Json -Depth 5

# 3) El backend ROTA el CSRF al loguear → pedirlo de nuevo
$r2 = Invoke-RestMethod -Uri "$Base/auth/csrf" -WebSession $sess
$csrf = $r2.csrf_token
Write-Host "== CSRF post-login: $csrf"

# 4) Sincronizar datos fluviales (esto es lo que querías)
Write-Host "`n== Sincronizando datos fluviales (puede tardar 1-3 min)..."
$sync = Invoke-RestMethod -Uri "$Base/api/modulo3/sincronizar-fluvial" `
    -Method Post -WebSession $sess -Headers @{ "X-CSRF-Token" = $csrf }
$sync | ConvertTo-Json -Depth 5

# 5) Generar zonas
Write-Host "`n== Generando zonas de riesgo..."
$gen = Invoke-RestMethod -Uri "$Base/api/modulo3/generar" `
    -Method Post -WebSession $sess -ContentType "application/json" `
    -Headers @{ "X-CSRF-Token" = $csrf } -Body '{"comunas":null}'
$gen | ConvertTo-Json -Depth 5

# 6) Listar zonas
Write-Host "`n== Zonas activas:"
$zonas = Invoke-RestMethod -Uri "$Base/api/modulo3/zonas" -WebSession $sess
$zonas | ConvertTo-Json -Depth 8