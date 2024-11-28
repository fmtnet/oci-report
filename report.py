import oci
import datetime
from datetime import timezone
from collections import defaultdict

# Inicializar cliente OCI
config = oci.config.from_file("~/.oci/config")  # Caminho padrão do arquivo config
monitoring_client = oci.monitoring.MonitoringClient(config)
cost_analysis_client = oci.usage_api.UsageapiClient(config)
compute_client = oci.core.ComputeClient(config)
identity_client = oci.identity.IdentityClient(config)

# Obter informações do tenancy
tenancy_id = config["tenancy"]
compartments = identity_client.list_compartments(
    tenancy_id, compartment_id_in_subtree=True, lifecycle_state="ACTIVE"
).data

# Ajustar datas para o início do dia
start_time = (datetime.datetime.now(timezone.utc) - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
end_time = datetime.datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# Função para coletar métricas
def get_metrics(namespace, resource_id, metric_name, compartment_id, start_time, end_time):
    response = monitoring_client.summarize_metrics_data(
        oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace=namespace,
            query=f"{metric_name}[1m].mean()",
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        ),
        compartment_id=compartment_id
    )
    return response.data

# Função para coletar custos
def get_costs(start_time, end_time):
    usage_request = oci.usage_api.models.RequestSummarizedUsagesDetails(
        tenant_id=tenancy_id,
        time_usage_started=start_time.isoformat(),
        time_usage_ended=end_time.isoformat(),
        granularity="DAILY"
    )
    response = cost_analysis_client.request_summarized_usages(usage_request)
    return response.data

# Coletar métricas de desempenho
performance_data = defaultdict(list)

for compartment in compartments:
    compartment_id = compartment.id

    # Coletar métricas de CPU para instâncias
    instances = compute_client.list_instances(compartment_id).data
    for instance in instances:
        if instance.lifecycle_state == "RUNNING":
            metrics = get_metrics(
                namespace="oci_computeagent",
                resource_id=instance.id,
                metric_name="CpuUtilization",
                compartment_id=compartment_id,
                start_time=start_time,
                end_time=end_time
            )
            performance_data[instance.display_name].append({
                "compartment": compartment.name,
                "metrics": metrics
            })

# Coletar custos
cost_data = get_costs(start_time, end_time)

# Gerar relatório de recursos ociosos
report = []

for instance, data in performance_data.items():
    avg_cpu_util = sum([d["metrics"][0].aggregated_datapoints[0].value for d in data]) / len(data)
    if avg_cpu_util < 5:  # Definindo 5% de uso como threshold
        report.append({
            "instance_name": instance,
            "avg_cpu_util": avg_cpu_util,
            "compartment": data[0]["compartment"]
        })

# Relatório final
print("=== Relatório de Recursos Ociosos ===")
for item in report:
    print(f"Instância: {item['instance_name']} | CPU Média: {item['avg_cpu_util']}% | Compartimento: {item['compartment']}")

print("\n=== Custos por Serviço ===")
for cost in cost_data.items:
    # Verificar atributos disponíveis dinamicamente
    product_name = getattr(cost, 'description', "Serviço não identificado")
    computed_amount = getattr(cost, 'computed_amount', 0)
    currency = getattr(cost, 'currency', "USD")
    print(f"Serviço: {product_name} | Custo: {computed_amount} {currency}")
