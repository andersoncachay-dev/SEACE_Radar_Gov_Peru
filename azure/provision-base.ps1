$ErrorActionPreference = "Stop"

$resourceGroup = "govradar-rg"
$location = "centralus"
$registryName = "pgihughesnetacr"
$registryResourceGroup = "pgi-hughesnet-rg"
$environmentName = "managedEnvironment-pgihughesnetrg-8fab"
$environmentResourceGroup = "pgi-hughesnet-rg"
$identityName = "govradar-identity"
$vaultName = "govradarkv923fd1"
$postgresName = "govradar-db-rodar"
$postgresDatabase = "govradar"
$postgresAdmin = "govradaradmin"

if ((& az provider show --namespace Microsoft.KeyVault --query registrationState -o tsv) -ne "Registered") {
    & az provider register --namespace Microsoft.KeyVault --wait
    if ($LASTEXITCODE -ne 0) { throw "No se pudo registrar Microsoft.KeyVault" }
}

function Invoke-AzTsv {
    param([string[]]$Arguments)
    $result = & az @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Azure CLI failed: az $($Arguments -join ' ')" }
    return ($result | Out-String).Trim()
}

function Get-AzOptionalTsv {
    param([string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $result = & az @Arguments 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($exitCode -ne 0) { return "" }
    return ($result | Out-String).Trim()
}

function Ensure-RoleAssignment {
    param([string]$PrincipalId, [string]$PrincipalType, [string]$Role, [string]$Scope)
    $existing = Invoke-AzTsv @(
        "role", "assignment", "list",
        "--assignee-object-id", $PrincipalId,
        "--role", $Role,
        "--scope", $Scope,
        "--query", "[0].id",
        "-o", "tsv"
    )
    if (-not $existing) {
        & az role assignment create `
            --assignee-object-id $PrincipalId `
            --assignee-principal-type $PrincipalType `
            --role $Role `
            --scope $Scope `
            --only-show-errors `
            -o none
        if ($LASTEXITCODE -ne 0) { throw "No se pudo asignar el rol $Role" }
    }
}

function Set-KeyVaultSecretWithRetry {
    param([string]$VaultName, [string]$SecretName, [string]$SecretValue)
    for ($attempt = 1; $attempt -le 18; $attempt++) {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & az keyvault secret set --vault-name $VaultName --name $SecretName --value $SecretValue --only-show-errors -o none 2>$null
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
        if ($exitCode -eq 0) { return }
        Start-Sleep -Seconds 10
    }
    throw "No se pudo guardar el secreto $SecretName después de esperar la propagación RBAC"
}

if ((Invoke-AzTsv @("group", "exists", "--name", $resourceGroup)) -ne "true") {
    & az group create --name $resourceGroup --location $location --tags application=govradar owner=rodar -o none
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el grupo de recursos" }
}

$environmentId = Invoke-AzTsv @("containerapp", "env", "show", "--resource-group", $environmentResourceGroup, "--name", $environmentName, "--query", "id", "-o", "tsv")

$identityId = Get-AzOptionalTsv @("identity", "show", "--resource-group", $resourceGroup, "--name", $identityName, "--query", "id", "-o", "tsv")
if (-not $identityId) {
    & az identity create --resource-group $resourceGroup --name $identityName --location $location -o none
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la identidad administrada" }
}
$identityId = Invoke-AzTsv @("identity", "show", "--resource-group", $resourceGroup, "--name", $identityName, "--query", "id", "-o", "tsv")
$identityPrincipalId = Invoke-AzTsv @("identity", "show", "--resource-group", $resourceGroup, "--name", $identityName, "--query", "principalId", "-o", "tsv")
$acrId = Invoke-AzTsv @("acr", "show", "--resource-group", $registryResourceGroup, "--name", $registryName, "--query", "id", "-o", "tsv")
Ensure-RoleAssignment -PrincipalId $identityPrincipalId -PrincipalType "ServicePrincipal" -Role "AcrPull" -Scope $acrId

$vaultId = Get-AzOptionalTsv @("keyvault", "show", "--resource-group", $resourceGroup, "--name", $vaultName, "--query", "id", "-o", "tsv")
if (-not $vaultId) {
    & az keyvault create `
        --resource-group $resourceGroup `
        --name $vaultName `
        --location $location `
        --enable-rbac-authorization true `
        --enable-purge-protection true `
        -o none
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear Key Vault" }
}
$vaultId = Invoke-AzTsv @("keyvault", "show", "--resource-group", $resourceGroup, "--name", $vaultName, "--query", "id", "-o", "tsv")
Ensure-RoleAssignment -PrincipalId $identityPrincipalId -PrincipalType "ServicePrincipal" -Role "Key Vault Secrets User" -Scope $vaultId
$currentUserObjectId = Invoke-AzTsv @("ad", "signed-in-user", "show", "--query", "id", "-o", "tsv")
Ensure-RoleAssignment -PrincipalId $currentUserObjectId -PrincipalType "User" -Role "Key Vault Administrator" -Scope $vaultId

$postgresId = Get-AzOptionalTsv @("postgres", "flexible-server", "show", "--resource-group", $resourceGroup, "--name", $postgresName, "--query", "id", "-o", "tsv")
if (-not $postgresId) {
    $postgresPassword = "GvR!Aa1" + [Guid]::NewGuid().ToString("N")
    & az postgres flexible-server create `
        --resource-group $resourceGroup `
        --name $postgresName `
        --location $location `
        --admin-user $postgresAdmin `
        --admin-password $postgresPassword `
        --version 16 `
        --tier Burstable `
        --sku-name Standard_B1ms `
        --storage-size 32 `
        --backup-retention 14 `
        --geo-redundant-backup Disabled `
        --public-access 0.0.0.0 `
        --yes `
        -o none
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear PostgreSQL" }
    Set-KeyVaultSecretWithRetry -VaultName $vaultName -SecretName "postgres-admin-password" -SecretValue $postgresPassword
} else {
    $postgresPassword = Get-AzOptionalTsv @("keyvault", "secret", "show", "--vault-name", $vaultName, "--name", "postgres-admin-password", "--query", "value", "-o", "tsv")
    if (-not $postgresPassword) {
        $postgresPassword = "GvR!Aa1" + [Guid]::NewGuid().ToString("N")
        & az postgres flexible-server update --resource-group $resourceGroup --name $postgresName --admin-password $postgresPassword -o none
        if ($LASTEXITCODE -ne 0) { throw "No se pudo restablecer el password PostgreSQL" }
        Set-KeyVaultSecretWithRetry -VaultName $vaultName -SecretName "postgres-admin-password" -SecretValue $postgresPassword
    }
}

if (-not (Get-AzOptionalTsv @("postgres", "flexible-server", "db", "show", "--resource-group", $resourceGroup, "--server-name", $postgresName, "--name", $postgresDatabase, "--query", "name", "-o", "tsv"))) {
    & az postgres flexible-server db create --resource-group $resourceGroup --server-name $postgresName --name $postgresDatabase -o none
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la base GovRadar" }
}

$databaseUrl = "postgresql+psycopg://${postgresAdmin}:$postgresPassword@$postgresName.postgres.database.azure.com:5432/$postgresDatabase`?sslmode=require"
$appSecret = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
$adminPassword = "Gov!Aa1" + [Guid]::NewGuid().ToString("N")

Set-KeyVaultSecretWithRetry -VaultName $vaultName -SecretName "database-url" -SecretValue $databaseUrl
Set-KeyVaultSecretWithRetry -VaultName $vaultName -SecretName "app-secret-key" -SecretValue $appSecret
if (-not (Get-AzOptionalTsv @("keyvault", "secret", "show", "--vault-name", $vaultName, "--name", "admin-password", "--query", "id", "-o", "tsv"))) {
    Set-KeyVaultSecretWithRetry -VaultName $vaultName -SecretName "admin-password" -SecretValue $adminPassword
}

[PSCustomObject]@{
    ResourceGroup = $resourceGroup
    ContainerAppsEnvironment = $environmentId
    PostgreSQL = $postgresName
    Database = $postgresDatabase
    KeyVault = $vaultName
    ManagedIdentity = $identityName
    Registry = "$registryName.azurecr.io"
} | Format-List
