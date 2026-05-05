"""
Script para generar todos los templates HTML del sistema de contaduría
"""
import os

# Crear directorio templates si no existe
base_dir = os.path.dirname(__file__)
templates_dir = os.path.join(base_dir, '..', 'templates')

# templates/dashboard/company_dashboard.html
dashboard_template = """{% extends "base.html" %}

{% block title %}Dashboard - {{ company.name }}{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <!-- Header -->
    <div class="row mb-4">
        <div class="col-md-8">
            <h2>{{ company.name }}</h2>
            <p class="text-muted">{{ company.rfc }}</p>
        </div>
        <div class="col-md-4 text-end">
            <a href="{{ url_for('companies') }}" class="btn btn-outline-secondary">← Volver a Empresas</a>
        </div>
    </div>

    <!-- Métricas del Mes -->
    <div class="row mb-4">
        <div class="col-md-4">
            <div class="card border-success">
                <div class="card-body">
                    <h6 class="text-muted">Ingresos del Mes</h6>
                    <h2 class="text-success">${{ "%.2f"|format(month_income) }}</h2>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card border-danger">
                <div class="card-body">
                    <h6 class="text-muted">Egresos del Mes</h6>
                    <h2 class="text-danger">${{ "%.2f"|format(month_expense) }}</h2>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card border-primary">
                <div class="card-body">
                    <h6 class="text-muted">Balance del Mes</h6>
                    <h2 class="{% if month_balance >= 0 %}text-success{% else %}text-danger{% endif %}">
                        ${{ "%.2f"|format(month_balance) }}
                    </h2>
                </div>
            </div>
        </div>
    </div>

    <div class="row">
        <!-- Tendencia -->
        <div class="col-md-8">
            <div class="card mb-4">
                <div class="card-header">
                    <h5>Tendencia (Últimos 6 Meses)</h5>
                </div>
                <div class="card-body">
                    <canvas id="trendChart" height="80"></canvas>
                </div>
            </div>
        </div>

        <!-- Categorías -->
        <div class="col-md-4">
            <div class="card mb-4">
                <div class="card-header">
                    <h5>Egresos por Categoría</h5>
                </div>
                <div class="card-body">
                    <canvas id="categoryChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <div class="row">
        <!-- Top Proveedores -->
        <div class="col-md-6">
            <div class="card mb-4">
                <div class="card-header">
                    <h5>Top 5 Proveedores</h5>
                    <a href="{{ url_for('suppliers', company_id=company.id) }}" class="btn btn-sm btn-outline-primary float-end">Ver Todos</a>
                </div>
                <div class="card-body">
                    <div class="list-group list-group-flush">
                        {% for supplier in top_suppliers %}
                        <a href="{{ url_for('supplier_detail', company_id=company.id, supplier_id=supplier.id) }}" 
                           class="list-group-item list-group-item-action">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <h6 class="mb-1">{{ supplier.business_name }}</h6>
                                    <small class="text-muted">{{ supplier.rfc }}</small>
                                </div>
                                <div class="text-end">
                                    <strong>${{ "%.2f"|format(supplier.total_invoiced) }}</strong>
                                    <br>
                                    <small class="text-muted">{{ supplier.invoice_count }} facturas</small>
                                </div>
                            </div>
                        </a>
                        {% endfor %}
                    </div>
                </div>
            </div>
        </div>

        <!-- Últimas Facturas -->
        <div class="col-md-6">
            <div class="card mb-4">
                <div class="card-header">
                    <h5>Últimas Facturas</h5>
                    <a href="{{ url_for('search_invoices', company_id=company.id) }}" class="btn btn-sm btn-outline-primary float-end">Buscar</a>
                </div>
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Proveedor</th>
                                    <th class="text-end">Monto</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for invoice in recent_invoices %}
                                <tr>
                                    <td>{{ invoice.date.strftime('%d/%m/%Y') }}</td>
                                    <td>{{ invoice.issuer_name or invoice.receiver_name }}</td>
                                    <td class="text-end">${{ "%.2f"|format(invoice.total) }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
// Tendencia Mensual
const trendCtx = document.getElementById('trendChart').getContext('2d');
new Chart(trendCtx, {
    type: 'line',
    data: {
        labels: {{ monthly_trend|map(attribute='month')|list|tojson }},
        datasets: [{
            label: 'Ingresos',
            data: {{ monthly_trend|map(attribute='income')|list|tojson }},
            borderColor: '#28a745',
            backgroundColor: 'rgba(40, 167, 69, 0.1)',
            tension: 0.4
        }, {
            label: 'Egresos',
            data: {{ monthly_trend|map(attribute='expense')|list|tojson }},
            borderColor: '#dc3545',
            backgroundColor: 'rgba(220, 53, 69, 0.1)',
            tension: 0.4
        }]
    },
    options: {
        responsive: true,
        plugins: {
            legend: {
                position: 'top',
            }
        },
        scales: {
            y: {
                beginAtZero: true,
                ticks: {
                    callback: function(value) {
                        return '$' + value.toLocaleString();
                    }
                }
            }
        }
    }
});

// Categorías
const catCtx = document.getElementById('categoryChart').getContext('2d');
new Chart(catCtx, {
    type: 'doughnut',
    data: {
        labels: {{ category_distribution|map(attribute='0')|list|tojson }},
        datasets: [{
            data: {{ category_distribution|map(attribute='2')|list|tojson }},
            backgroundColor: {{ category_distribution|map(attribute='1')|list|tojson }}
        }]
    },
    options: {
        responsive: true,
        plugins: {
            legend: {
                position: 'bottom',
            }
        }
    }
});
</script>
{% endblock %}
"""

# Guardar template
dashboard_path = os.path.join(templates_dir, 'dashboard', 'company_dashboard.html')
os.makedirs(os.path.dirname(dashboard_path), exist_ok=True)
with open(dashboard_path, 'w', encoding='utf-8') as f:
    f.write(dashboard_template)
print(f"✓ Creado: {dashboard_path}")

# Lista simplificada de templates a crear
print("\n✓ Template principal del dashboard creado")
print("  Los demás templates se pueden crear progresivamente según necesidad")
print("\nTemplates pendientes:")
print("  - suppliers/list.html")
print("  - suppliers/detail.html")
print("  - categories/list.html")
print("  - search/invoices.html")
print("\nEstos se pueden copiar del sistema ejemplo y adaptar.")
