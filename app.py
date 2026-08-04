from flask import Flask, render_template, jsonify, request
import mysql.connector
from datetime import datetime, timedelta, date
from collections import defaultdict
import math
import calendar
import config

app = Flask(__name__)

AFORO_MAXIMO = 200

INTERVALS = [
    ("6:30–7:00",  6, 30, 7,  0),
    ("7:00–7:30",  7,  0, 7, 30),
    ("7:30–8:00",  7, 30, 8,  0),
    ("8:00–8:30",  8,  0, 8, 30),
]
INTERVAL_NAMES = [iv[0] for iv in INTERVALS]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
MESES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
          7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
SCHOOL_MONTHS = [8,9,10,11,12,1,2,3,4,5,6,7]

# Mapea los alias usados en el código ("adultos","ninos","registro_escaneos")
# a los nombres reales de base de datos definidos en el .env
DB_NAME_MAP = {
    "adultos": config.DB_NAME_ADULTOS,
    "ninos": config.DB_NAME_NINOS,
    "registro_escaneos": config.DB_NAME_REGISTROS,
}

def conn(db):
    nombre_real = DB_NAME_MAP.get(db, db)
    return mysql.connector.connect(**config.mysql_connector_config(nombre_real))

def fetch_personas():
    out = {}
    for db, tbl, tipo in [("adultos","ADULTOS","Adulto"),("ninos","NINOS","Niño")]:
        try:
            c = conn(db)
            cur = c.cursor(dictionary=True)
            cur.execute(f"SELECT ID, NOMBRE, APELLIDOS FROM `{tbl}`")
            for r in cur.fetchall():
                out[str(r["ID"]).strip()] = {
                    "nombre": str(r["NOMBRE"] or "").strip(),
                    "apellidos": str(r["APELLIDOS"] or "").strip(),
                    "tipo": tipo,
                }
            cur.close(); c.close()
        except Exception as e:
            print(f"Error {db}: {e}")
    return out

def interval_idx(dt):
    t = dt.hour * 60 + dt.minute
    for i, (_, h1, m1, h2, m2) in enumerate(INTERVALS):
        if h1*60+m1 <= t < h2*60+m2:
            return i
    return -1

def enrich(rows, personas):
    records = []
    for r in rows:
        fh = r["fecha_hora"]
        code = str(r["codigo"]).strip()
        p = personas.get(code, {"nombre":"?","apellidos":"","tipo":"Desconocido"})
        records.append({
            "codigo": code,
            "nombre": p["nombre"],
            "apellidos": p["apellidos"],
            "tipo": p["tipo"],
            "fecha": fh.date(),
            "dow": fh.weekday(),
            "interval": interval_idx(fh),
        })
    return records

def compute_lambdas(records):
    days_per_dow = defaultdict(set)
    day_ivl = defaultdict(int)
    for r in records:
        if r["interval"] >= 0:
            days_per_dow[r["dow"]].add(r["fecha"])
            day_ivl[(r["fecha"], r["dow"], r["interval"])] += 1

    lam = {}
    for d in range(5):
        n = len(days_per_dow[d])
        lam[d] = {}
        for iv in range(4):
            if n == 0:
                lam[d][iv] = 0.0
            else:
                total = sum(day_ivl.get((fecha, d, iv), 0) for fecha in days_per_dow[d])
                lam[d][iv] = round(total / n, 2)
    return lam, days_per_dow, day_ivl

def poisson_ci(l):
    if l <= 0:
        return 0, 0
    std = math.sqrt(l)
    return max(0, int(l - 1.28*std)), int(l + 1.28*std + 0.5)

def lambda_table(lam):
    rows = []
    for iv in range(4):
        row = {"intervalo": INTERVAL_NAMES[iv]}
        for d in range(5):
            row[DIAS[d]] = lam[d][iv]
        row["lambda_promedio"] = round(sum(lam[d][iv] for d in range(5)) / 5, 2)
        rows.append(row)
    total = {"intervalo": "TOTAL"}
    for d in range(5):
        total[DIAS[d]] = round(sum(lam[d][iv] for iv in range(4)), 2)
    total["lambda_promedio"] = round(sum(total[DIAS[d]] for d in range(5)) / 5, 2)
    return rows, total

def fetch_estadisticas_asistentes(codigos_mes):
    """
    Dado un set de códigos que asistieron en el mes,
    regresa estadísticas demográficas separadas para Niños y Adultos.
    """
    stats = {"ninos": {}, "adultos": {}}

    if not codigos_mes:
        return stats

    ph = ",".join(["%s"] * len(codigos_mes))
    ids = list(codigos_mes)

    # ── NIÑOS ──────────────────────────────────────────────────────────────
    try:
        c = conn("ninos")
        cur = c.cursor(dictionary=True)
        cur.execute(f"""
            SELECT GENERO, EDAD, DOMICILIO, COLONIA, MUNICIPIO,
                   GRADO_ESC, ESCUELA
            FROM NINOS
            WHERE ID IN ({ph})
        """, ids)
        rows = cur.fetchall()
        cur.close(); c.close()

        def _count(rows, key):
            d = defaultdict(int)
            for r in rows:
                val = str(r.get(key) or "Sin dato").strip()
                d[val] += 1
            return dict(sorted(d.items()))

        stats["ninos"] = {
            "total": len(rows),
            "genero":        _count(rows, "GENERO"),
            "edad":          _count(rows, "EDAD"),
            "domicilio":     _count(rows, "DOMICILIO"),
            "municipio":     _count(rows, "MUNICIPIO"),
            "colonia":       _count(rows, "COLONIA"),
            "grado_escolar": _count(rows, "GRADO_ESC"),
            "escuela":       _count(rows, "ESCUELA"),
        }
    except Exception as e:
        print(f"Error stats niños: {e}")
        stats["ninos"] = {"error": str(e)}

    # ── ADULTOS ────────────────────────────────────────────────────────────
    try:
        c = conn("adultos")
        cur = c.cursor(dictionary=True)
        cur.execute(f"""
            SELECT GENERO, EDAD, EDO_CIVIL, ESCOLARIDAD,
                   OCUPACION, DOMICILIO, COLONIA, MUNICIPIO
            FROM ADULTOS
            WHERE ID IN ({ph})
        """, ids)
        rows = cur.fetchall()
        cur.close(); c.close()

        stats["adultos"] = {
            "total": len(rows),
            "genero":       _count(rows, "GENERO"),
            "edad":         _count(rows, "EDAD"),
            "estado_civil": _count(rows, "EDO_CIVIL"),
            "escolaridad":  _count(rows, "ESCOLARIDAD"),
            "ocupacion":    _count(rows, "OCUPACION"),
            "domicilio":    _count(rows, "DOMICILIO"),
            "colonia":      _count(rows, "COLONIA"),
            "municipio":    _count(rows, "MUNICIPIO"),
        }
    except Exception as e:
        print(f"Error stats adultos: {e}")
        stats["adultos"] = {"error": str(e)}

    return stats

@app.errorhandler(mysql.connector.Error)
def handle_db_error(e):
    print(f"Error de MySQL: {e}")
    return jsonify({
        "error": "No se pudo conectar a la base de datos. "
                 "Verifica que MySQL esté corriendo y que las credenciales en .env sean correctas."
    }), 503

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/mensual")
def api_mensual():
    year  = int(request.args.get("year",  datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))

    personas = fetch_personas()
    c = conn("registro_escaneos")
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT codigo, fecha_hora FROM registros WHERE YEAR(fecha_hora)=%s AND MONTH(fecha_hora)=%s", (year, month))
    rows = cur.fetchall(); cur.close(); c.close()

    recs = enrich(rows, personas)
    total   = len(recs)
    adultos = sum(1 for r in recs if r["tipo"]=="Adulto")
    ninos   = sum(1 for r in recs if r["tipo"]=="Niño")

    unique_days  = set(r["fecha"] for r in recs)
    n_days = len(unique_days)
    prom   = round(total/n_days, 1) if n_days else 0
    pct    = round(prom/AFORO_MAXIMO*100, 2)

    day_tot      = defaultdict(int)
    days_per_dow = defaultdict(set)
    for r in recs:
        day_tot[r["dow"]] += 1
        days_per_dow[r["dow"]].add(r["fecha"])

    dia_mas   = max(day_tot, key=day_tot.get) if day_tot else -1
    dia_menos = min(day_tot, key=day_tot.get) if day_tot else -1

    s3 = []
    total_general = len(recs)
    for d in range(5):
        t = day_tot.get(d,0); n = len(days_per_dow[d])
        a = sum(1 for r in recs if r["dow"]==d and r["tipo"]=="Adulto")
        ni = sum(1 for r in recs if r["dow"]==d and r["tipo"]=="Niño")
        s3.append({"dia":DIAS[d],"total":t,"promedio":round(t/n,1) if n else 0,
                   "adultos":a,"ninos":ni,
                   "pct_adultos":round(a/t*100,1) if t else 0,
                   "pct_ninos":round(ni/t*100,1) if t else 0,
                   "pct_total":round(t/total_general*100,1) if total_general else 0})

    lam, dpd, div = compute_lambdas(recs)
    s4_rows, s4_total = lambda_table(lam)

    # Próximo día = día siguiente al registro más reciente.
    # Si ese día-de-semana no tiene datos históricos, avanzar hasta encontrar uno que sí tenga.
    ultimo_registro = max((r["fecha"] for r in recs), default=date(year, month, 1))
    next_day = ultimo_registro + timedelta(days=1)
    for _ in range(7):
        dow_candidate = next_day.weekday()
        if dow_candidate < 5 and any(lam[dow_candidate][iv] > 0 for iv in range(4)):
            break
        next_day += timedelta(days=1)
    ndow = next_day.weekday()
    if ndow not in lam:
        # No se encontró ningún día hábil con datos históricos en los próximos 7 días
        # (mes con muy pocos registros entre semana). Usamos lunes como referencia
        # por default; lam[0] existirá siempre (con ceros si no hay datos).
        ndow = 0
    n_ndow = len(dpd.get(ndow, set()))
    max_n  = max((len(v) for v in dpd.values()), default=1)

    peak_freq = defaultdict(int); peak_total = 0
    for fecha in dpd.get(ndow, set()):
        cnts = [div.get((fecha, ndow, iv), 0) for iv in range(4)]
        if any(cnts):
            peak_freq[cnts.index(max(cnts))] += 1
            peak_total += 1

    s5 = []
    for iv in range(4):
        l = lam[ndow][iv]; mn, mx = poisson_ci(l)
        pp   = round(peak_freq[iv]/peak_total*100, 2) if peak_total else 0
        conf = round(n_ndow/max(max_n,1)*100) if max_n else 0
        s5.append({"intervalo":INTERVAL_NAMES[iv],"esperadas":round(l),
                   "minimo":mn,"maximo":mx,"prob_hora_pico":pp,
                   "confiabilidad":conf,
                   "nivel":"Alta" if conf>=80 else "Media" if conf>=50 else "Baja"})
        
    # ── Sección 8 — Estadísticas demográficas de asistentes únicos del mes ──
    codigos_ninos   = set(r["codigo"] for r in recs if r["tipo"] == "Niño")
    codigos_adultos = set(r["codigo"] for r in recs if r["tipo"] == "Adulto")
    s8 = fetch_estadisticas_asistentes(codigos_ninos | codigos_adultos)
    # Sobreescribir totales con únicos reales separados
    s8["ninos"]["asistentes_unicos"]   = len(codigos_ninos)
    s8["adultos"]["asistentes_unicos"] = len(codigos_adultos)

    code_cnt = defaultdict(int)
    for r in recs: code_cnt[r["codigo"]] += 1
    top10 = [{"rank":i+1,"id":c,"nombre":recs_by_code(c,recs)["nombre"],
               "apellidos":recs_by_code(c,recs)["apellidos"],"tipo":recs_by_code(c,recs)["tipo"],"asistencias":n}
             for i,(c,n) in enumerate(sorted(code_cnt.items(),key=lambda x:-x[1])[:10])]

    # Sección 7 — comidas por día (desglose diario del mes)
    by_date = defaultdict(lambda: defaultdict(int))
    for r in recs:
        by_date[r["fecha"]][r["codigo"]] += 1

    DIAS_FULL = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    s7 = []
    for d in sorted(by_date.keys()):
        entries = sorted(
            [{"id": c,
              "nombre": recs_by_code(c, recs)["nombre"],
              "apellidos": recs_by_code(c, recs)["apellidos"],
              "tipo": recs_by_code(c, recs)["tipo"],
              "apariciones": n}
             for c, n in by_date[d].items()],
            key=lambda x: -x["apariciones"]
        )
        s7.append({
            "fecha": d.strftime("%Y-%m-%d"),
            "fecha_display": d.strftime("%d/%m/%Y"),
            "dia_semana": DIAS_FULL[d.weekday()],
            "total": sum(e["apariciones"] for e in entries),
            "entradas": entries,
        })


    return jsonify({
        "mes":MESES.get(month,"?"), "year":year, "aforo_maximo":AFORO_MAXIMO,
        "s1":{"total":total,"promedio_diario":prom,
              "dia_mas":DIAS[dia_mas] if 0<=dia_mas<5 else "-",
              "dia_menos":DIAS[dia_menos] if 0<=dia_menos<5 and dia_menos!=dia_mas else "-",
              "pct_capacidad":pct},
        "s2":{"adultos":adultos,"ninos":ninos,"total":total,
              "adultos_prom":round(adultos/n_days,1) if n_days else 0,
              "ninos_prom":round(ninos/n_days,1) if n_days else 0,
              "pct_adultos":round(adultos/total*100,2) if total else 0,
              "pct_ninos":round(ninos/total*100,2) if total else 0},
        "s3":s3, "s4":{"tabla":s4_rows,"total":s4_total},
        "s5":{"next_day":DIAS[ndow] if ndow<5 else ["Sábado","Domingo"][ndow-5],
              "next_fecha":next_day.strftime("%d/%m/%Y"),"predicciones":s5,
              "total_dia":sum(p["esperadas"] for p in s5)},
        "s6":top10,
        "s7":s7,
        "s8":s8,
    })

def recs_by_code(code, recs):
    for r in recs:
        if r["codigo"] == code:
            return r
    return {"nombre":"?","apellidos":"","tipo":"?"}



@app.route("/api/anual")
def api_anual():
    sy = int(request.args.get("year", datetime.now().year))

    personas = fetch_personas()
    c = conn("registro_escaneos")
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT codigo, fecha_hora FROM registros WHERE fecha_hora >= %s AND fecha_hora <= %s",
                (datetime(sy,8,1), datetime(sy+1,7,31,23,59,59)))
    rows = cur.fetchall(); cur.close(); c.close()

    recs = enrich(rows, personas)
    total_year = len(recs)
    adultos    = sum(1 for r in recs if r["tipo"]=="Adulto")
    ninos      = sum(1 for r in recs if r["tipo"]=="Niño")

    n_days    = len(set(r["fecha"] for r in recs))
    prom_dia  = round(total_year/n_days,1) if n_days else 0
    pct_cap   = round(prom_dia/AFORO_MAXIMO*100, 2)

    active_months = set((r["fecha"].year, r["fecha"].month) for r in recs)
    n_months  = len(active_months)
    prom_men  = round(total_year/n_months,1) if n_months else 0

    month_data = []
    for m in SCHOOL_MONTHS:
        yr = sy if m >= 8 else sy+1
        mr = [r for r in recs if r["fecha"].month==m and r["fecha"].year==yr]
        mt = len(mr); md = len(set(r["fecha"] for r in mr))
        ma = sum(1 for r in mr if r["tipo"]=="Adulto")
        mn = sum(1 for r in mr if r["tipo"]=="Niño")
        mp = round(mt/md,1) if md else 0
        ivl_c = defaultdict(int)
        for r in mr:
            if r["interval"]>=0: ivl_c[r["interval"]] += 1
        pk = max(ivl_c,key=ivl_c.get) if ivl_c else -1
        month_data.append({"mes":MESES[m],"total":mt,"dias_habiles":md,
                            "promedio_diario":mp,"adultos":ma,"ninos":mn,
                            "pct_adultos":round(ma/mt*100,2) if mt else 0,
                            "pct_ninos":round(mn/mt*100,2) if mt else 0,
                            "pct_capacidad":round(mp/AFORO_MAXIMO*100,2) if mt else 0,
                            "hora_pico":INTERVAL_NAMES[pk] if pk>=0 else "-"})

    active = [d for d in month_data if d["total"]>0]
    mes_mas   = max(active, key=lambda d:d["total"])["mes"] if active else "-"
    mes_menos = min(active, key=lambda d:d["total"])["mes"] if active else "-"

    day_tot = defaultdict(int)
    dpd     = defaultdict(set)
    for r in recs:
        day_tot[r["dow"]] += 1; dpd[r["dow"]].add(r["fecha"])

    total_general_anual = len(recs)
    s3 = []
    for d in range(5):
        t  = day_tot.get(d,0)
        a  = sum(1 for r in recs if r["dow"]==d and r["tipo"]=="Adulto")
        ni = sum(1 for r in recs if r["dow"]==d and r["tipo"]=="Niño")
        s3.append({"dia":DIAS[d],"total":t,
                   "promedio":round(t/len(dpd[d]),1) if dpd[d] else 0,
                   "adultos":a,"ninos":ni,
                   "pct_adultos":round(a/t*100,1) if t else 0,
                   "pct_ninos":round(ni/t*100,1) if t else 0,
                   "pct_total":round(t/total_general_anual*100,1) if total_general_anual else 0})

    lam, _, _ = compute_lambdas(recs)
    s4_rows, s4_total = lambda_table(lam)

    code_cnt = defaultdict(int)
    for r in recs: code_cnt[r["codigo"]] += 1
    top10 = [{"rank":i+1,"id":c,**personas.get(c,{"nombre":"?","apellidos":"","tipo":"?"}),"asistencias":n}
             for i,(c,n) in enumerate(sorted(code_cnt.items(),key=lambda x:-x[1])[:10])]

    # ── S6: Estadísticas demográficas anuales ──
    codigos_anio = set(r["codigo"] for r in recs)
    s6 = fetch_estadisticas_asistentes(codigos_anio)
    s6["ninos"]["asistentes_unicos"]   = sum(1 for c in codigos_anio if personas.get(c,{}).get("tipo")=="Niño")
    s6["adultos"]["asistentes_unicos"] = sum(1 for c in codigos_anio if personas.get(c,{}).get("tipo")=="Adulto")

    

    return jsonify({
        "ciclo":f"{sy}–{sy+1}",
        "s1":{"total_year":total_year,"prom_mensual":prom_men,"prom_diario":prom_dia,
              "adultos":adultos,"ninos":ninos,"mes_mas":mes_mas,"mes_menos":mes_menos,
              "pct_cap":pct_cap},
        "s2":month_data,"s3":s3,"s4":{"tabla":s4_rows,"total":s4_total},"s5":top10,
        "s6":s6
    })

@app.route("/api/perfiles")
def api_perfiles():
    ids = [i.strip() for i in request.args.get("ids","").split(",") if i.strip()]
    if not ids:
        return jsonify({"error":"No se proporcionaron IDs"}), 400

    personas = fetch_personas()
    c = conn("registro_escaneos")
    cur = c.cursor(dictionary=True)
    ph = ",".join(["%s"]*len(ids))
    cur.execute(f"SELECT codigo, fecha_hora FROM registros WHERE codigo IN ({ph})", ids)
    rows = cur.fetchall(); cur.close(); c.close()

    profiles = []
    for pid in ids:
        p = personas.get(pid, {"nombre":"Desconocido","apellidos":"","tipo":"?"})
        pr = [r for r in rows if str(r["codigo"]).strip()==pid]
        total = len(pr)
        fechas = [r["fecha_hora"] for r in pr]
        primera = min(fechas).strftime("%d/%m/%Y") if fechas else "-"
        ultima  = max(fechas).strftime("%d/%m/%Y") if fechas else "-"

        mes_c = defaultdict(int)
        dow_c = defaultdict(int)
        ivl_c = defaultdict(int)
        for r in pr:
            fh = r["fecha_hora"]
            mes_c[fh.month] += 1
            if fh.weekday()<5: dow_c[fh.weekday()] += 1
            iv = interval_idx(fh)
            if iv>=0: ivl_c[iv] += 1

        profiles.append({
            "id":pid,**p,"total":total,"primera_visita":primera,"ultima_visita":ultima,
            "por_mes":{MESES.get(m,str(m)):cnt for m,cnt in sorted(mes_c.items())},
            "por_dia":[{"dia":DIAS[d],"count":dow_c.get(d,0)} for d in range(5)],
            "por_intervalo":[{"intervalo":INTERVAL_NAMES[iv],"count":ivl_c.get(iv,0)} for iv in range(4)],
        })
    return jsonify({"perfiles":profiles})

@app.route("/api/fechas")
def api_fechas():
    ini_s = request.args.get("inicio")
    fin_s = request.args.get("fin")
    if not ini_s:
        return jsonify({"error":"Fecha de inicio requerida"}), 400
    try:
        ini = datetime.strptime(ini_s, "%Y-%m-%d")
        fin = datetime.strptime(fin_s, "%Y-%m-%d") if fin_s else ini
        fin = fin.replace(hour=23, minute=59, second=59)
    except ValueError:
        return jsonify({"error":"Formato inválido. Use YYYY-MM-DD"}), 400

    personas = fetch_personas()
    c = conn("registro_escaneos")
    cur = c.cursor(dictionary=True)
    cur.execute("SELECT codigo, fecha_hora FROM registros WHERE fecha_hora >= %s AND fecha_hora <= %s ORDER BY fecha_hora", (ini, fin))
    rows = cur.fetchall(); cur.close(); c.close()

    by_date = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_date[r["fecha_hora"].date()][str(r["codigo"]).strip()] += 1

    result = []
    for d in sorted(by_date.keys()):
        entries = sorted([{"id":c,**personas.get(c,{"nombre":"?","apellidos":"","tipo":"?"}),"apariciones":n}
                          for c,n in by_date[d].items()], key=lambda x:-x["apariciones"])
        wd = d.weekday()
        dname = DIAS[wd] if wd<5 else ["Sábado","Domingo"][wd-5]
        result.append({"fecha":d.strftime("%Y-%m-%d"),"dia_semana":dname,
                       "total":sum(e["apariciones"] for e in entries),"entradas":entries})

    code_total = defaultdict(int)
    for d_data in by_date.values():
        for c,n in d_data.items(): code_total[c] += n
    resumen = sorted([{"id":c,**personas.get(c,{"nombre":"?","apellidos":"","tipo":"?"}),"total":n}
                      for c,n in code_total.items()], key=lambda x:-x["total"])

    return jsonify({"inicio":ini_s,"fin":fin_s or ini_s,"total_registros":len(rows),
                    "por_fecha":result,"resumen":resumen})

if __name__ == "__main__":
    app.run(debug=config.FLASK_DEBUG, host=config.FLASK_HOST, port=config.FLASK_PORT)