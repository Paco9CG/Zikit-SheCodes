"""CLI y orquestador para benchmark, predicción y servicio web (Zero-dependency)."""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.detector import EarlyWarningDetector
from src.evaluator import BenchmarkEvaluator
from src.preprocessor import TelemetryPreprocessor


def cmd_benchmark(args):
    raiz = Path(args.data_dir)
    corridas_dir = raiz / "corridas"
    evaluator = BenchmarkEvaluator(raiz)

    indices = []
    if args.corridas == "todas" or args.corridas == "1-10":
        indices = list(range(1, 11))
    else:
        for p in args.corridas.split(","):
            if "-" in p:
                start, end = map(int, p.split("-"))
                indices.extend(range(start, end + 1))
            else:
                indices.append(int(p))

    print(f"\n=======================================================")
    print(f" EJECUTANDO BENCHMARK LOCAL SOBRE CORRIDAS {indices}")
    print(f"=======================================================\n")

    res_globales = []
    for idx in indices:
        carpeta = corridas_dir / f"corrida_{idx:02d}"
        if not (carpeta / "_solucion").exists():
            print(f"[!] Saltando {carpeta.name} (sin _solucion)")
            continue
        print(f"-> Evaluando {carpeta.name}...")
        res = evaluator.evaluar_corrida(carpeta)
        res_globales.append(res)
        print(f"   Aciertos (TP): {res['aciertos_tp']}/{res['total_incidentes_reales']} | "
              f"Falsas alarmas: {res['falsas_alarmas_fp']} | "
              f"Precision: {res['precision']:.2%} | "
              f"Recall: {res['recall']:.2%} | "
              f"Lead Time prom: {res['lead_time_promedio_horas']}h")

    if not res_globales:
        print("[!] No se encontraron corridas evaluables.")
        return

    # Resumen general
    total_reales = sum(r["total_incidentes_reales"] for r in res_globales)
    total_tp = sum(r["aciertos_tp"] for r in res_globales)
    total_fp = sum(r["falsas_alarmas_fp"] for r in res_globales)
    total_fn = sum(r["no_detectados_fn"] for r in res_globales)

    precision_global = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall_global = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1_global = 2 * precision_global * recall_global / (precision_global + recall_global) if (precision_global + recall_global) > 0 else 0

    all_leads = [ac["lead_time_min"] for r in res_globales for ac in r["detalle_aciertos"]]
    lead_prom_min = sum(all_leads) / len(all_leads) if all_leads else 0

    print("\n" + "=" * 60)
    print(" RESULTADOS CONSOLIDADOS DEL BENCHMARK")
    print("=" * 60)
    print(f"  Total incidentes reales:    {total_reales}")
    print(f"  Incidentes detectados (TP): {total_tp}")
    print(f"  No detectados (FN):         {total_fn}")
    print(f"  Falsas alarmas (FP):        {total_fp}")
    print(f"  Precisión global:           {precision_global:.2%}")
    print(f"  Recall global:              {recall_global:.2%}")
    print(f"  F1-Score global:            {f1_global:.4f}")
    print(f"  Anticipación promedio:      {lead_prom_min:.1f} minutos ({lead_prom_min/60.0:.2f} horas)")
    print("=" * 60 + "\n")


def cmd_predict(args):
    raiz = Path(args.data_dir)
    corridas_dir = raiz / "corridas"
    salida_csv = Path(args.output)
    salida_csv.parent.mkdir(parents=True, exist_ok=True)

    indices = []
    if args.corridas == "todas" or args.corridas == "11-54":
        indices = list(range(11, 55))
    elif args.corridas == "1-54":
        indices = list(range(1, 55))
    else:
        for p in args.corridas.split(","):
            if "-" in p:
                start, end = map(int, p.split("-"))
                indices.extend(range(start, end + 1))
            else:
                indices.append(int(p))

    print(f"\n=======================================================")
    print(f" GENERANDO ALERTAS DE DETECCION SOBRE CORRIDAS {args.corridas}")
    print(f"=======================================================\n")

    alertas_finales = []
    tenants = ["gracko", "gramo", "kaiku", "ttr"]

    for idx in indices:
        carpeta = corridas_dir / f"corrida_{idx:02d}"
        if not carpeta.exists():
            print(f"[!] No existe {carpeta.name}, saltando...")
            continue

        print(f"-> Procesando {carpeta.name}...")
        for tenant in tenants:
            ruta_tenant = carpeta / tenant
            ruta_metricas = ruta_tenant / "metricas.csv"
            if not ruta_metricas.exists():
                continue

            filas_crudo = TelemetryPreprocessor.cargar_metricas(ruta_metricas)
            detector = EarlyWarningDetector(tenant, ruta_tenant)

            for f in filas_crudo:
                alerta = detector.procesar_minuto(f)
                if alerta:
                    alerta_con_corrida = {
                        "corrida": carpeta.name,
                        **alerta
                    }
                    alertas_finales.append(alerta_con_corrida)

    # Exportar CSV usando csv.DictWriter
    # Siempre crear el archivo con encabezados, incluso si no hubo alertas.
    cols = ["corrida", "tenant", "timestamp", "confianza", "tipo_incidente"]
    alertas_finales.sort(key=lambda row: (row["corrida"], row["tenant"], row["timestamp"]))
    with salida_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in alertas_finales:
            writer.writerow({k: row.get(k, "") for k in cols})
    print(f"\n[OK] Generadas {len(alertas_finales)} alertas guardadas en: {salida_csv}")


def cmd_serve(args):
    from src.api import start_server
    start_server(host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(description="Sistema de Alerta Temprana — Antes de que suene el teléfono")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Benchmark subparser
    p_bench = subparsers.add_parser("benchmark", help="Ejecutar benchmark de evaluación sobre corridas con solución")
    p_bench.add_argument("--data-dir", default="data", help="Ruta al directorio data/")
    p_bench.add_argument("--corridas", default="1-10", help="Rango de corridas a evaluar (ej. 1-10, 1,2,3)")
    p_bench.set_defaults(func=cmd_benchmark)

    # Predict subparser
    p_pred = subparsers.add_parser("predict", help="Generar alertas tempranas para evaluación/competencia")
    p_pred.add_argument("--data-dir", default="data", help="Ruta al directorio data/")
    p_pred.add_argument("--corridas", default="11-54", help="Rango de corridas a predecir (ej. 11-54, 1-54)")
    p_pred.add_argument("--output", default="outputs/alertas.csv", help="Archivo CSV de salida")
    p_pred.set_defaults(func=cmd_predict)

    # Serve subparser
    p_serve = subparsers.add_parser("serve", help="Levantar servidor web y API")
    p_serve.add_argument("--host", default="0.0.0.0", help="Host de escucha")
    p_serve.add_argument("--port", type=int, default=8000, help="Puerto de escucha")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
