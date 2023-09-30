import pulumi
import pulumi_azure as azure
import pulumi_azuread as azuread
from pulumi_azure_native import authorization,keyvault

config              = pulumi.Config("pulumi-az-sp")
prefix              = config.require("prefix")
location            = config.require("location") or "east us"
subscription_id     = authorization.get_client_config().subscription_id
tenant_id           = authorization.get_client_config().tenant_id
resource_group      = config.require("rg")
key_vault           = config.require("kv")
sample_secret_value = config.require("sample-secret-value")


# Create Azure AD Application for AKS
app = azuread.Application(
    f"{prefix}-microk8s-app",
    display_name=f"{prefix}-microk8s-app"
)

# Create service principal for the application
sp = azuread.ServicePrincipal(
    f"{prefix}-microk8s-sp",
    application_id=app.application_id
)

apppwd = azuread.ApplicationPassword(
  f"{prefix}-microk8s-pwd",
  application_object_id=app.object_id,
  display_name=f"{prefix}-microk8s-pwd",
  end_date="2099-01-01T00:00:00Z"
)

kv = azure.keyvault.KeyVault.get(
  resource_name=key_vault,
  id=f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.KeyVault/vaults/{key_vault}",
  opts=pulumi.ResourceOptions(protect=True)
)


# Grant AKS access to the Key Vault secrets
aks_access_policy = azure.keyvault.AccessPolicy(f"{prefix}-aks-kv-access-policy",
  key_vault_id=kv.id,
  tenant_id=tenant_id,
  object_id=sp.object_id,
  secret_permissions=["Get"]
)

# Create a key vault secret
sample_secret = keyvault.Secret("sample-secret",
  resource_group_name=resource_group,
  vault_name=kv.name,
  secret_name="sample-secret",
  properties=keyvault.SecretPropertiesArgs(
    value=sample_secret_value,
  )
)

pulumi.export("tenant id", tenant_id)
pulumi.export("client id", app.application_id)
pulumi.export("object id", app.object_id)
pulumi.export("client secret", apppwd.value)
pulumi.export("vault name", kv.name)
