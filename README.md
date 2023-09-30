# k8s-secrets-sync-kv-beta
Sync k8s secret with Azure Key Vault

# Setup

Login into Azure:

```bash
az login --use-device-code
```

## Pulumi 

Create an Azure Service Principal:

```bash
pulumi -C pulumi-az-sp stack init dev
export PULUMI_CONFIG_PASSPHRASE="<your passphrase>"
pulumi -C pulumi-az-sp config set pulumi-az-sp:prefix pulumi
pulumi -C pulumi-az-sp config set pulumi-az-sp:location <location>
pulumi -C pulumi-az-sp config set pulumi-az-sp:kv <key vault>
pulumi -C pulumi-az-sp config set pulumi-az-sp:rg <resource group>
pulumi -C pulumi-az-sp config set --secret pulumi-az-sp:sample-secret-value asecretvalue
pulumi -C pulumi-az-sp up
export CLIENT_ID=`pulumi -C pulumi-az-sp stack output 'client id'`
export CLIENT_SECRET=`pulumi -C pulumi-az-sp stack output 'client secret' --show-secrets`
export TENANT_ID=`pulumi -C pulumi-az-sp stack output 'tenant id'`
export VAULT_NAME=`pulumi -C pulumi-az-sp stack output 'vault name'`
```

# Microk8s

```bash
sudo snap install microk8s --classic
microk8s status --wait-ready
microk8s config | tee ~/.kube/microk8s
chmod 0600 ~/.kube/microk8s
export KUBECONFIG=~/.kube/microk8s 
microk8s enable hostpath-storage
```

### Install the Secrets Store CSI Driver and the Azure Keyvault Provider 

[Azure Key Vault Provider for Secrets Store CSI Driver](https://github.com/Azure/secrets-store-csi-driver-provider-azure)

>>> Azure Key Vault provider for Secrets Store CSI Driver allows you to get secret contents stored in an Azure Key Vault instance and use the Secrets Store CSI driver interface to mount them into Kubernetes pods.

```bash
kubectl apply -f microk8s-demo/00_namespace.yaml
kubectl -n azure-kv-sync create secret generic secrets-store-creds --from-literal clientid="$CLIENT_ID" --from-literal clientsecret="$CLIENT_SECRET"
kubectl -n azure-kv-sync label secret secrets-store-creds secrets-store.csi.k8s.io/used=true
```

```bash
helm repo add csi-secrets-store-provider-azure https://azure.github.io/secrets-store-csi-driver-provider-azure/charts
helm install csi-secrets-store-provider-azure  \
  csi-secrets-store-provider-azure/csi-secrets-store-provider-azure \
  --namespace kube-system \
  --set secrets-store-csi-driver.syncSecret.enabled=true \
  --set secrets-store-csi-driver.enableSecretRotation=true \
  --set linux.kubeletRootDir=/var/snap/microk8s/common/var/lib/kubelet
```

## Install the External Secrets Operator

[External Secrets Operator](https://external-secrets.io/latest/)

>>> External Secrets Operator is a Kubernetes operator that integrates external secret management systems like AWS Secrets Manager, HashiCorp Vault, Google Secrets Manager, Azure Key Vault, IBM Cloud Secrets Manager, CyberArk Conjur and many more.

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets \
   external-secrets/external-secrets \
    -n external-secrets \
    --create-namespace
```

## Install the Reloader

[Reloader](https://github.com/stakater/Reloader)

>>> Reloader can watch changes in ConfigMap and Secret and do rolling upgrades on Pods with their associated DeploymentConfigs, Deployments, Daemonsets Statefulsets and Rollouts.

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm install stakater/reloader \
  --set resourceLabelSelector=reloader=enabled \
  --namespace reloader \
  --create-namespace \
  --generate-name
```

# Install the demo app

```bash
yq --inplace ".spec.parameters.tenantId = \"$TENANT_ID\"" microk8s-demo/01_secretProviderClass.yaml
yq --inplace "select(.kind == \"SecretStore\").spec.provider.azurekv.tenantId = \"$TENANT_ID\"" microk8s-demo/02_externalSecrets.yaml
yq --inplace ".spec.parameters.keyvaultName = \"$VAULT_NAME\"" microk8s-demo/01_secretProviderClass.yaml
yq --inplace "select(.kind == \"SecretStore\").spec.provider.azurekv.vaultUrl = \"https://$VAULT_NAME.vault.azure.net\"" microk8s-demo/02_externalSecrets.yaml
kubectl apply -f microk8s-demo/01_secretProviderClass.yaml
kubectl apply -f microk8s-demo/02_externalSecrets.yaml
kubectl apply -f microk8s-demo/03_demo.yaml
```

## Check secrets

```bash
kubectl -n azure-kv-sync get secrets csi-sample-secret -o jsonpath="{.data.sample-secret}" | base64 -d
kubectl -n azure-kv-sync get secrets eso-sample-secret -o jsonpath="{.data.sample-secret}" | base64 -d
kubectl -n azure-kv-sync exec -t deployments/busybox-secrets-store-inline -- sh -c 'echo $SECRET_CSI'
kubectl -n azure-kv-sync exec -t deployments/busybox-secrets-store-inline -- sh -c 'echo $SECRET_ESO'
```

Monioring the secret environment variables

```bash
while true; do kubectl -n azure-kv-sync exec -t deployments/busybox-secrets-store-inline -- sh -c 'env | grep ^SECRET'; echo; sleep 1; done
```

Notice:
* `eso-sample-secret` is refreshed every 5 seconds ( declared in the manifest )
* `csi-sample-secret` is refreshed every 2 minutes ( [default value](https://github.com/Azure/secrets-store-csi-driver-provider-azure/blob/b2cf91c02d02e88cba3c997aa4af19c7ecd61d8e/charts/csi-secrets-store-provider-azure/values.yaml#L159) )

## Cleanup

```bash
sudo snap remove microk8s
pulumi -C pulumi-az-sp destroy
pulumi -C pulumi-az-sp stack rm dev
az logout
```

Notice: secret in Azure Key Vault must be eventually purged.

