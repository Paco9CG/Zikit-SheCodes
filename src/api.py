"""Servidor HTTP y API Dashboard ultra veloz (Carga instantánea con cache y paginación)."""
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import csv
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from src.evaluator import BenchmarkEvaluator

DATA_DIR = Path("data")
OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
ALERTAS_CSV = OUTPUTS_DIR / "alertas.csv"
BENCHMARK_CACHE_FILE = OUTPUTS_DIR / "benchmark_cache.json"

_cache_base = {}
_cache_alertas = []
_simulaciones = {
    "alertas_simuladas": [],
    "falsas_simuladas": [],
}


def cargar_cache_alertas(forzar_recarga: bool = False):
    global _cache_alertas
    if _cache_alertas and not forzar_recarga:
        return _cache_alertas
    if ALERTAS_CSV.exists():
        with ALERTAS_CSV.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            _cache_alertas = list(reader)
    return _cache_alertas



def obtener_base_benchmark():
    global _cache_base
    if _cache_base:
        return _cache_base

    # 1. Intentar cargar desde el archivo de cache pre-generado (0ms)
    if BENCHMARK_CACHE_FILE.exists():
        try:
            _cache_base = json.loads(BENCHMARK_CACHE_FILE.read_text(encoding="utf-8"))
            return _cache_base
        except Exception:
            pass

    # 2. Si no existe cache, calcular una sola vez
    evaluator = BenchmarkEvaluator(DATA_DIR)
    res_list = []
    senuelos_totales = []
    falsas_totales = []

    for i in range(1, 11):
        c_path = DATA_DIR / "corridas" / f"corrida_{i:02d}"
        if (c_path / "_solucion").exists():
            r = evaluator.evaluar_corrida(c_path)
            res_list.append(r)
            c_name = r["corrida"]
            for s in r.get("senuelos_neutralizados", []):
                senuelos_totales.append({
                    "corrida": c_name,
                    "tenant": s["tenant"],
                    "timestamp": s["timestamp"].isoformat() if hasattr(s["timestamp"], "isoformat") else str(s["timestamp"]),
                    "tipo": s["tipo"],
                    "estado": "Neutralizado (Sin alerta emitida)",
                })
            for fa in r.get("detalle_falsas_alarmas", []):
                falsas_totales.append({
                    "corrida": c_name,
                    "tenant": fa["tenant"],
                    "timestamp": fa["timestamp"].isoformat() if hasattr(fa["timestamp"], "isoformat") else str(fa["timestamp"]),
                    "tipo": fa.get("tipo", "Desconocido"),
                    "motivo": fa.get("motivo", "Falsa alarma"),
                })

    total_reales = sum(r["total_incidentes_reales"] for r in res_list)
    total_tp = sum(r["aciertos_tp"] for r in res_list)
    total_fp = sum(r["falsas_alarmas_fp"] for r in res_list)
    total_fn = sum(r["no_detectados_fn"] for r in res_list)
    leads = [ac["lead_time_min"] for r in res_list for ac in r["detalle_aciertos"]]
    avg_lead_min = sum(leads) / len(leads) if leads else 0

    _cache_base = {
        "total_incidentes_reales": total_reales,
        "aciertos_tp": total_tp,
        "falsas_alarmas_fp": total_fp,
        "no_detectados_fn": total_fn,
        "lead_time_promedio_horas": round(avg_lead_min / 60.0, 2),
        "corridas": res_list,
        "senuelos_totales": senuelos_totales,
        "falsas_alarmas_totales": falsas_totales,
    }
    
    # Guardar cache a disco para futuros arranques instantáneos
    try:
        BENCHMARK_CACHE_FILE.write_text(json.dumps(_cache_base, default=str), encoding="utf-8")
    except Exception:
        pass

    return _cache_base


def calcular_benchmark_actual():
    base = obtener_base_benchmark()
    tp_sim = len(_simulaciones["alertas_simuladas"])
    fp_sim = len(_simulaciones["falsas_simuladas"])

    total_reales = base["total_incidentes_reales"] + tp_sim
    aciertos_tp = base["aciertos_tp"] + tp_sim
    falsas_alarmas_fp = base["falsas_alarmas_fp"] + fp_sim
    no_detectados_fn = base["no_detectados_fn"]

    precision = aciertos_tp / (aciertos_tp + falsas_alarmas_fp) if (aciertos_tp + falsas_alarmas_fp) > 0 else 0
    recall = aciertos_tp / total_reales if total_reales > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    falsas_combinadas = _simulaciones["falsas_simuladas"] + base["falsas_alarmas_totales"]

    return {
        "total_incidentes_reales": total_reales,
        "aciertos_tp": aciertos_tp,
        "falsas_alarmas_fp": falsas_alarmas_fp,
        "no_detectados_fn": no_detectados_fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "lead_time_promedio_horas": base["lead_time_promedio_horas"],
        "senuelos_totales": base["senuelos_totales"],
        "falsas_alarmas_totales": falsas_combinadas,
        "simulaciones_activas": {
            "alertas_reales": tp_sim,
            "falsas_alarmas": fp_sim,
        }
    }


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reto Zikit</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Inter', sans-serif; }</style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Toast de notificación -->
        <div id="toast-container" class="fixed top-5 right-5 z-50 flex flex-col gap-2 max-w-md"></div>

        <!-- Header -->
        <header class="flex flex-col lg:flex-row justify-between items-start lg:items-center pb-6 border-b border-slate-800 mb-8 gap-4">
            <div>
                <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-teal-400 to-indigo-400">
                    Reto Zikit - SheCodes
                </h1>
                <p class="text-slate-400 text-sm mt-1">Sistema de Alerta Temprana y Observabilidad Predictiva para PyMEs</p>
            </div>

            <!-- Panel de Controles y Simulador -->
            <div class="flex flex-wrap items-center gap-3">
                <div class="flex items-center gap-2 bg-slate-800/90 p-1.5 rounded-xl border border-slate-700 shadow-md">
                    <span class="text-xs font-semibold text-slate-300 px-2 flex items-center gap-1.5">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        Simulador:
                    </span>
                    <select id="sim-tenant" class="bg-slate-900 border border-slate-700 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500">
                        <option value="gracko">Gracko (Contable)</option>
                        <option value="gramo">Gramo (Alimentos)</option>
                        <option value="kaiku">Kaiku (E-commerce)</option>
                        <option value="ttr">TTR (Logística)</option>
                    </select>
                    <button onclick="ejecutarSimulacion('real')" class="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-3 py-1.5 rounded-lg text-xs transition flex items-center gap-1 shadow">
                        <span>🚨</span> Incidencia Real
                    </button>
                    <button onclick="ejecutarSimulacion('falsa')" class="bg-rose-600 hover:bg-rose-500 text-white font-medium px-3 py-1.5 rounded-lg text-xs transition flex items-center gap-1 shadow">
                        <span>⚠️</span> Falsa Alarma
                    </button>
                    <button onclick="restablecerSimulacion()" class="bg-slate-700 hover:bg-slate-600 text-slate-300 font-medium px-2 py-1.5 rounded-lg text-xs transition flex items-center gap-1" title="Restablecer simulación">
                        <span>🔄</span> Reset
                    </button>
                </div>

                <a href="/api/export" class="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-3.5 py-2 rounded-lg text-xs transition shadow-lg shadow-indigo-600/30 flex items-center gap-1.5">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    Descargar CSV
                </a>
            </div>
        </header>

        <!-- KPI Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-slate-800/80 p-5 rounded-xl border border-slate-700/60 shadow-lg">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">% Alertas Reales</span>
                <div class="text-3xl font-bold mt-2" id="kpi-recall">Cargando...</div>
                <span class="text-xs" id="kpi-tp">Calculando...</span>
            </div>
            <div class="bg-slate-800/80 p-5 rounded-xl border border-slate-700/60 shadow-lg">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">% Falsas Alarmas</span>
                <div class="text-3xl font-bold mt-2" id="kpi-fp-val">0%</div>
                <span class="text-xs font-semibold" id="kpi-fp-label">100% Señuelos Neutralizados</span>
            </div>
            <div class="bg-slate-800/80 p-5 rounded-xl border border-slate-700/60 shadow-lg">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Anticipación Promedio</span>
                <div class="text-3xl font-bold text-amber-400 mt-2" id="kpi-lead">Cargando...</div>
                <span class="text-xs text-slate-400">Lead time antes del impacto</span>
            </div>
            <div class="bg-slate-800/80 p-5 rounded-xl border border-slate-700/60 shadow-lg">
                <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cobertura de Incidentes</span>
                <div class="text-3xl font-bold text-indigo-400 mt-2" id="kpi-cobertura">100.0%</div>
                <span class="text-xs text-slate-400" id="kpi-cobertura-sub">Incidentes detectados a tiempo</span>
            </div>
        </div>

        <!-- Navegación por Pestañas -->
        <div class="flex border-b border-slate-700 mb-6 gap-2">
            <button onclick="cambiarPestana('alertas')" id="tab-btn-alertas" class="px-5 py-2.5 font-medium text-sm rounded-t-lg transition border-b-2 border-indigo-500 bg-slate-800 text-white">
                Alertas Tempranas Emitidas (<span id="count-tab-alertas">0</span>)
            </button>
            <button onclick="cambiarPestana('senuelos')" id="tab-btn-senuelos" class="px-5 py-2.5 font-medium text-sm rounded-t-lg transition border-b-2 border-transparent text-slate-400 hover:text-slate-200">
                Señuelos Benignos Neutralizados (<span id="count-tab-senuelos">0</span>)
            </button>
            <button onclick="cambiarPestana('falsas')" id="tab-btn-falsas" class="px-5 py-2.5 font-medium text-sm rounded-t-lg transition border-b-2 border-transparent text-slate-400 hover:text-slate-200">
                Falsas Alarmas Cometidas (<span id="count-tab-falsas">0</span>)
            </button>
        </div>

        <!-- Vista 1: Alertas Emitidas -->
        <div id="vista-alertas" class="bg-slate-800/80 rounded-xl border border-slate-700/60 overflow-hidden shadow-lg">
            <div class="p-4 border-b border-slate-700 flex flex-wrap justify-between items-center gap-3 bg-slate-900/40">
                <div>
                    <h2 class="text-base font-semibold text-white">Alertas Reales Emitidas (Incidentes Tempranos)</h2>
                    <p class="text-xs text-slate-400">Alertas enviadas antes del impacto del cliente.</p>
                </div>
                <!-- Filtros y Paginador -->
                <div class="flex items-center gap-3">
                    <select id="filtro-tenant-alertas" onchange="filtrarAlertas()" class="bg-slate-800 border border-slate-700 text-xs rounded-lg px-2.5 py-1.5 text-slate-200">
                        <option value="todos">Todos los Tenants</option>
                        <option value="gracko">Gracko</option>
                        <option value="gramo">Gramo</option>
                        <option value="kaiku">Kaiku</option>
                        <option value="ttr">TTR</option>
                    </select>
                    <div class="flex items-center gap-1.5 text-xs text-slate-400">
                        <button onclick="paginaPrev()" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-slate-200">&larr;</button>
                        <span id="page-info-alertas">Pág 1 de 1</span>
                        <button onclick="paginaNext()" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-slate-200">&rarr;</button>
                    </div>
                </div>
            </div>
            <div class="overflow-x-auto min-h-[300px]">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-900/80 text-xs uppercase text-slate-400 sticky top-0">
                        <tr>
                            <th class="px-5 py-3">Corrida</th>
                            <th class="px-5 py-3">Tenant</th>
                            <th class="px-5 py-3">Timestamp Alerta</th>
                            <th class="px-5 py-3">Tipo Incidente</th>
                            <th class="px-5 py-3">Confianza</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-alertas" class="divide-y divide-slate-700/50 font-mono text-xs">
                        <tr><td colspan="5" class="px-5 py-8 text-center text-slate-500 font-sans">Cargando alertas de forma instantánea...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Vista 2: Señuelos Neutralizados -->
        <div id="vista-senuelos" class="hidden bg-slate-800/80 rounded-xl border border-slate-700/60 overflow-hidden shadow-lg">
            <div class="p-4 border-b border-slate-700 flex justify-between items-center bg-slate-900/40">
                <div>
                    <h2 class="text-base font-semibold text-teal-400">Señuelos y Eventos Benignos Identificados</h2>
                    <p class="text-xs text-slate-400">Respaldos nocturnos, nóminas y promociones que el detector suprimió con éxito.</p>
                </div>
            </div>
            <div class="overflow-x-auto max-h-[550px]">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-900/80 text-xs uppercase text-slate-400 sticky top-0">
                        <tr>
                            <th class="px-5 py-3">Corrida</th>
                            <th class="px-5 py-3">Tenant</th>
                            <th class="px-5 py-3">Inicio Señuelo</th>
                            <th class="px-5 py-3">Tipo Señuelo</th>
                            <th class="px-5 py-3">Acción del Detector</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-senuelos" class="divide-y divide-slate-700/50 font-mono text-xs">
                        <tr><td colspan="5" class="px-5 py-8 text-center text-slate-500 font-sans">Cargando señuelos...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Vista 3: Falsas Alarmas Cometidas -->
        <div id="vista-falsas" class="hidden bg-slate-800/80 rounded-xl border border-slate-700/60 overflow-hidden shadow-lg">
            <div class="p-4 border-b border-slate-700 flex justify-between items-center bg-slate-900/40">
                <div>
                    <h2 class="text-base font-semibold text-rose-400">Falsas Alarmas Cometidas (Errores de Predicción)</h2>
                    <p class="text-xs text-slate-400">Alertas emitidas cuando no había ningún incidente real en curso.</p>
                </div>
            </div>
            <div class="p-8 text-center" id="empty-falsas">
                <div class="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 mb-3">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                </div>
                <h3 class="text-lg font-semibold text-white">¡Cero Falsas Alarmas en el Detector!</h3>
                <p class="text-sm text-slate-400 mt-1 max-w-md mx-auto">Puedes usar el botón superior <strong>«Simular Falsa Alarma»</strong> para probar cómo se registraría un error en esta tabla y su impacto en la precisión.</p>
            </div>
            <div class="overflow-x-auto max-h-[550px] hidden" id="table-falsas-container">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-900/80 text-xs uppercase text-slate-400 sticky top-0">
                        <tr>
                            <th class="px-5 py-3">Corrida</th>
                            <th class="px-5 py-3">Tenant</th>
                            <th class="px-5 py-3">Timestamp Alarma</th>
                            <th class="px-5 py-3">Tipo Evento</th>
                            <th class="px-5 py-3">Motivo del Error</th>
                        </tr>
                    </thead>
                    <tbody id="tbody-falsas" class="divide-y divide-slate-700/50 font-mono text-xs"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let todasLasAlertas = [];
        let alertasFiltradas = [];
        let paginaActual = 1;
        const tamanoPagina = 50;

        function mostrarToast(mensaje, tipo = 'info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            const bg = tipo === 'error' ? 'bg-rose-900/90 border-rose-500 text-rose-200' :
                       tipo === 'success' ? 'bg-emerald-900/90 border-emerald-500 text-emerald-200' :
                       'bg-indigo-900/90 border-indigo-500 text-indigo-200';
            toast.className = `${bg} border px-4 py-3 rounded-lg text-xs shadow-xl flex items-center justify-between transition-all duration-300 transform translate-y-2 opacity-0`;
            toast.innerHTML = `<span>${mensaje}</span><button onclick="this.parentElement.remove()" class="ml-3 text-slate-400 hover:text-white">&times;</button>`;
            container.appendChild(toast);
            setTimeout(() => toast.classList.remove('translate-y-2', 'opacity-0'), 10);
            setTimeout(() => {
                toast.classList.add('opacity-0');
                setTimeout(() => toast.remove(), 300);
            }, 4500);
        }

        function cambiarPestana(pestana) {
            ['alertas', 'senuelos', 'falsas'].forEach(p => {
                const vista = document.getElementById('vista-' + p);
                const btn = document.getElementById('tab-btn-' + p);
                if (p === pestana) {
                    vista.classList.remove('hidden');
                    btn.classList.add('border-indigo-500', 'bg-slate-800', 'text-white');
                    btn.classList.remove('border-transparent', 'text-slate-400');
                } else {
                    vista.classList.add('hidden');
                    btn.classList.remove('border-indigo-500', 'bg-slate-800', 'text-white');
                    btn.classList.add('border-transparent', 'text-slate-400');
                }
            });
        }

        function renderizarPaginaAlertas() {
            const inicio = (paginaActual - 1) * tamanoPagina;
            const fin = inicio + tamanoPagina;
            const lote = alertasFiltradas.slice(inicio, fin);
            const totalPaginas = Math.ceil(alertasFiltradas.length / tamanoPagina) || 1;

            document.getElementById('page-info-alertas').innerText = `Pág ${paginaActual} de ${totalPaginas}`;
            const tbody = document.getElementById('tbody-alertas');

            if (lote.length > 0) {
                tbody.innerHTML = lote.map(a => `
                    <tr class="hover:bg-slate-700/30 transition ${a.es_simulada ? 'bg-emerald-950/20' : ''}">
                        <td class="px-5 py-2.5 font-semibold text-slate-400">
                            ${a.corrida || 'N/A'}
                            ${a.es_simulada ? '<span class="ml-1.5 text-[10px] bg-emerald-600/60 text-emerald-200 px-1.5 py-0.5 rounded font-sans">En Vivo</span>' : ''}
                        </td>
                        <td class="px-5 py-2.5 font-semibold text-indigo-400 uppercase">${a.tenant}</td>
                        <td class="px-5 py-2.5 text-slate-300">${a.timestamp}</td>
                        <td class="px-5 py-2.5 text-teal-300 font-sans font-semibold">${a.tipo_incidente || 'Desconocido'}</td>
                        <td class="px-5 py-2.5 text-amber-400 font-bold">${Math.round(parseFloat(a.confianza || 0) * 100)}%</td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="5" class="px-5 py-8 text-center text-slate-500 font-sans">No hay alertas que coincidan.</td></tr>';
            }
        }

        function filtrarAlertas() {
            const filtro = document.getElementById('filtro-tenant-alertas').value;
            if (filtro === 'todos') {
                alertasFiltradas = todasLasAlertas;
            } else {
                alertasFiltradas = todasLasAlertas.filter(a => a.tenant.toLowerCase() === filtro);
            }
            paginaActual = 1;
            renderizarPaginaAlertas();
        }

        function paginaPrev() {
            if (paginaActual > 1) {
                paginaActual--;
                renderizarPaginaAlertas();
            }
        }

        function paginaNext() {
            const totalPaginas = Math.ceil(alertasFiltradas.length / tamanoPagina) || 1;
            if (paginaActual < totalPaginas) {
                paginaActual++;
                renderizarPaginaAlertas();
            }
        }

        async function ejecutarSimulacion(tipo) {
            const tenant = document.getElementById('sim-tenant').value;
            try {
                const res = await fetch('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tipo: tipo, tenant: tenant })
                });
                if (res.ok) {
                    const data = await res.json();
                    if (tipo === 'real') {
                        mostrarToast(`🚨 ${data.mensaje}`, 'success');
                        cambiarPestana('alertas');
                    } else {
                        mostrarToast(`⚠️ ${data.mensaje}`, 'error');
                        cambiarPestana('falsas');
                    }
                    await cargarDatos();
                }
            } catch(e) {
                console.error(e);
            }
        }

        async function restablecerSimulacion() {
            try {
                const res = await fetch('/api/reset-simulation', { method: 'POST' });
                if (res.ok) {
                    mostrarToast("🔄 Simulación restablecida a los valores base del Benchmark", "info");
                    cambiarPestana('alertas');
                    await cargarDatos();
                }
            } catch(e) {
                console.error(e);
            }
        }

        async function cargarDatos() {
            try {
                // Carga ultrarrápida instantánea en una sola petición (0ms)
                const resAlerts = await fetch('/api/alerts');
                if (resAlerts.ok) {
                    const data = await resAlerts.json();
                    todasLasAlertas = data.alertas || [];
                    document.getElementById('count-tab-alertas').innerText = data.total;
                    filtrarAlertas();

                    // Métricas de % Alertas Reales vs % Falsas Alarmas
                    const totalAlertas = data.aciertos_tp + data.falsas_alarmas_fp;
                    const pctReales = data.porcentaje_reales !== undefined ? data.porcentaje_reales : 100;
                    const pctFalsas = data.porcentaje_falsas !== undefined ? data.porcentaje_falsas : 0;

                    const kpiRecall = document.getElementById('kpi-recall');
                    const kpiTp = document.getElementById('kpi-tp');
                    kpiRecall.innerText = `${pctReales.toFixed(1)}%`;

                    if (data.falsas_alarmas_fp > 0) {
                        kpiRecall.className = "text-3xl font-bold mt-2 text-amber-400";
                        kpiTp.className = "text-xs text-amber-300 font-semibold";
                        kpiTp.innerText = `${data.aciertos_tp} reales de ${totalAlertas} emitidas`;
                    } else {
                        kpiRecall.className = "text-3xl font-bold mt-2 text-teal-400";
                        kpiTp.className = "text-xs text-slate-400";
                        kpiTp.innerText = `${data.aciertos_tp} reales de ${totalAlertas} emitidas (0 falsas)`;
                    }

                    document.getElementById('kpi-lead').innerText = data.lead_time_promedio_horas + ' hrs';
                    document.getElementById('kpi-cobertura').innerText = `${(data.recall * 100).toFixed(1)}%`;
                    document.getElementById('kpi-cobertura-sub').innerText = `${data.aciertos_tp} de ${data.total_incidentes_reales} incidentes capturados`;

                    const fpVal = document.getElementById('kpi-fp-val');
                    const fpLbl = document.getElementById('kpi-fp-label');
                    fpVal.innerText = `${pctFalsas.toFixed(1)}%`;
                    document.getElementById('count-tab-falsas').innerText = data.falsas_alarmas_fp;

                    if (data.falsas_alarmas_fp > 0) {
                        fpVal.className = "text-3xl font-bold mt-2 text-rose-400";
                        fpLbl.className = "text-xs font-semibold text-rose-400";
                        fpLbl.innerText = `${data.falsas_alarmas_fp} falsa${data.falsas_alarmas_fp > 1 ? 's' : ''} alarmas (${pctFalsas.toFixed(1)}%)`;
                    } else {
                        fpVal.className = "text-3xl font-bold mt-2 text-emerald-400";
                        fpLbl.className = "text-xs font-semibold text-emerald-400";
                        fpLbl.innerText = "0% Falsas (100% Neutras)";
                    }

                    // Señuelos
                    const senuelos = data.senuelos_totales || [];
                    document.getElementById('count-tab-senuelos').innerText = senuelos.length;
                    const tbodySen = document.getElementById('tbody-senuelos');
                    tbodySen.innerHTML = senuelos.map(s => `
                        <tr class="hover:bg-slate-700/30 transition">
                            <td class="px-5 py-2.5 text-slate-400 font-semibold">${s.corrida}</td>
                            <td class="px-5 py-2.5 font-semibold text-indigo-400 uppercase">${s.tenant}</td>
                            <td class="px-5 py-2.5 text-slate-300">${s.timestamp}</td>
                            <td class="px-5 py-2.5 text-amber-300 font-sans">${s.tipo}</td>
                            <td class="px-5 py-2.5 text-emerald-400 font-sans flex items-center gap-1.5">
                                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                                ${s.estado}
                            </td>
                        </tr>
                    `).join('');

                    // Falsas alarmas
                    const falsas = data.falsas_alarmas_totales || [];
                    if (falsas.length > 0) {
                        document.getElementById('empty-falsas').classList.add('hidden');
                        document.getElementById('table-falsas-container').classList.remove('hidden');
                        const tbodyFa = document.getElementById('tbody-falsas');
                        tbodyFa.innerHTML = falsas.map(fa => `
                            <tr class="hover:bg-slate-700/30 transition ${fa.es_simulada ? 'bg-rose-950/20' : ''}">
                                <td class="px-5 py-2.5 text-slate-400 font-semibold">
                                    ${fa.corrida}
                                    ${fa.es_simulada ? '<span class="ml-1.5 text-[10px] bg-rose-600/60 text-rose-200 px-1.5 py-0.5 rounded font-sans">Simulada</span>' : ''}
                                </td>
                                <td class="px-5 py-2.5 text-rose-400 uppercase font-bold">${fa.tenant}</td>
                                <td class="px-5 py-2.5 text-slate-300">${fa.timestamp}</td>
                                <td class="px-5 py-2.5 font-semibold text-amber-300">${fa.tipo}</td>
                                <td class="px-5 py-2.5 text-rose-300 font-sans">${fa.motivo}</td>
                            </tr>
                        `).join('');
                    } else {
                        document.getElementById('empty-falsas').classList.remove('hidden');
                        document.getElementById('table-falsas-container').classList.add('hidden');
                    }
                }
            } catch(e) {
                console.error("Error al cargar datos:", e);
            }
        }
        cargarDatos();
    </script>
</body>
</html>
"""


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))

        elif path == "/api/benchmark":
            data = calcular_benchmark_actual()
            payload = json.dumps(data, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/alerts":
            alertas = cargar_cache_alertas()
            todas = _simulaciones["alertas_simuladas"] + alertas
            bench = calcular_benchmark_actual()
            
            aciertos_tp = bench.get("aciertos_tp", 120)
            falsas_fp = bench.get("falsas_alarmas_fp", 0)
            total_evaluadas = aciertos_tp + falsas_fp
            pct_reales = round((aciertos_tp / total_evaluadas * 100), 1) if total_evaluadas > 0 else 100.0
            pct_falsas = round((falsas_fp / total_evaluadas * 100), 1) if total_evaluadas > 0 else 0.0

            data = {
                "total": len(todas),
                "alertas": todas,
                "aciertos_tp": aciertos_tp,
                "falsas_alarmas_fp": falsas_fp,
                "porcentaje_reales": pct_reales,
                "porcentaje_falsas": pct_falsas,
                "total_incidentes_reales": bench.get("total_incidentes_reales", 120),
                "lead_time_promedio_horas": bench.get("lead_time_promedio_horas", 17.97),
                "recall": bench.get("recall", 1.0),
                "senuelos_totales": bench.get("senuelos_totales", []),
                "falsas_alarmas_totales": bench.get("falsas_alarmas_totales", []),
            }
            payload = json.dumps(data, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/export":
            if ALERTAS_CSV.exists():
                contenido = ALERTAS_CSV.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", 'attachment; filename="alertas.csv"')
                self.send_header("Content-Length", str(len(contenido)))
                self.end_headers()
                self.wfile.write(contenido)
            else:
                self.send_error(404, "outputs/alertas.csv no encontrado")

        else:
            self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path

        if path == "/api/simulate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                req = json.loads(body)
            except Exception:
                req = {}

            tipo = req.get("tipo", "real")
            tenant = req.get("tenant", "gracko")
            ahora_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            if tipo == "real":
                incidente_tipo = {
                    "gracko": "deriva_disco",
                    "gramo": "fuga_memoria_worker",
                    "kaiku": "saturacion_bd_gradual",
                    "ttr": "crecimiento_cache_gps",
                }.get(tenant, "deriva_disco")

                alerta_sim = {
                    "corrida": "Simulación [En Vivo]",
                    "tenant": tenant,
                    "timestamp": ahora_iso,
                    "confianza": 0.94,
                    "tipo_incidente": incidente_tipo,
                    "es_simulada": True,
                }
                _simulaciones["alertas_simuladas"].insert(0, alerta_sim)

                # Notificar por Infobip SMS para incidencias reales
                sid_sms = None
                sms_info = ""
                try:
                    from src.notifier import notificar_incidencia_real
                    sid_sms = notificar_incidencia_real(tenant, incidente_tipo, 0.94, ahora_iso)
                    if sid_sms:
                        sms_info = f" [Se ha enviado un SMS con éxito.]"
                    else:
                        sms_info = " [SMS Infobip intentado - ver detalle de API/Credenciales en consola]"
                except Exception as err:
                    print(f"[!] Error enviando SMS Infobip: {err}")
                    sms_info = f" [Error SMS: {err}]"

                resultado = {
                    "mensaje": f"Incidencia Real simulada en {tenant.upper()}: '{incidente_tipo}' detectada con 94% de confianza.{sms_info}",
                    "alerta": alerta_sim,
                    "tipo": "real",
                    "sms_sid": sid_sms,
                }
            else:
                senuelo_tipo = {
                    "gracko": "respaldo_nocturno (23:00)",
                    "gramo": "promo_2x1 (Restaurantes)",
                    "kaiku": "campana_correo (Marketing)",
                    "ttr": "pedido_urgente (Rutas)",
                }.get(tenant, "respaldo_nocturno")

                falsa_sim = {
                    "corrida": "Simulación [En Vivo]",
                    "tenant": tenant,
                    "timestamp": ahora_iso,
                    "tipo": senuelo_tipo,
                    "motivo": f"Falsa Alarma: el detector alertó erróneamente durante el evento benigno '{senuelo_tipo}'.",
                    "es_simulada": True,
                }
                _simulaciones["falsas_simuladas"].insert(0, falsa_sim)
                resultado = {
                    "mensaje": f"Falsa Alarma simulada en {tenant.upper()}: alerta errónea disparada durante '{senuelo_tipo}'.",
                    "falsa_alarma": falsa_sim,
                    "tipo": "falsa",
                }

            payload = json.dumps(resultado, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/reset-simulation":
            _simulaciones["alertas_simuladas"].clear()
            _simulaciones["falsas_simuladas"].clear()
            payload = json.dumps({"mensaje": "Simulación restablecida con éxito"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        else:
            self.send_error(404, "Ruta no encontrada")


def start_server(host: str = "0.0.0.0", port: int = 8000):
    server = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    print(f"\n[+] Servidor web iniciado exitosamente en http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Deteniendo servidor...")
        server.server_close()
