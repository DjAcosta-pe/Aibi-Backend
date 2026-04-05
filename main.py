from fastapi import FastAPI, Request
from groq import Groq
from supabase import create_client
from datetime import datetime, timezone, date
import json, os, random, httpx

app = FastAPI()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
sb = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

TIPS = [
    "Ahorrar el 10% de cada ingreso es el primer paso hacia la libertad financiera.",
    "Regla 50/30/20: 50% necesidades, 30% deseos, 20% ahorro.",
    "Un fondo de emergencia de 3 meses de gastos te protege de cualquier imprevisto.",
    "Los pequenos gastos diarios pueden sumar mas de S/300 al mes sin que te des cuenta.",
    "El mejor momento para ahorrar fue ayer. El segundo mejor momento es hoy.",
    "Pagar tus deudas primero es la mejor inversion que puedes hacer.",
    "Registrar tus gastos diariamente tarda menos de 30 segundos y puede cambiar tu vida.",
    "El 78% de personas que registran sus gastos logran sus metas de ahorro.",
    "No se trata de cuanto ganas, sino de cuanto guardas.",
]

MONEDAS = {
    "PEN": {"nombre": "Soles peruanos", "simbolo": "S/", "tasa": 1.0},
    "USD": {"nombre": "Dolares americanos", "simbolo": "$", "tasa": 0.267},
    "EUR": {"nombre": "Euros", "simbolo": "€", "tasa": 0.244},
    "COP": {"nombre": "Pesos colombianos", "simbolo": "COP", "tasa": 1052.0},
    "MXN": {"nombre": "Pesos mexicanos", "simbolo": "MXN", "tasa": 4.55},
    "CLP": {"nombre": "Pesos chilenos", "simbolo": "CLP", "tasa": 243.0},
    "BRL": {"nombre": "Reales brasileños", "simbolo": "R$", "tasa": 1.33},
}

CATEGORIAS_DEFAULT = [
    "Comida", "Transporte", "Salud", "Entretenimiento",
    "Trabajo", "Ahorro", "Educacion", "Hogar", "Ropa", "Otro"
]

def tip():
    return f"\n\nTip Aibi: {random.choice(TIPS)}"

def simbolo(moneda):
    return MONEDAS.get(moneda, {}).get("simbolo", "S/")

def fmt(monto, moneda="PEN"):
    return f"{simbolo(moneda)} {monto:.0f}"

async def enviar(chat_id, texto):
    async with httpx.AsyncClient() as c:
        await c.post(f"{TELEGRAM_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": texto
        })

async def enviar_botones(chat_id, texto, botones):
    teclado = {"inline_keyboard": botones}
    async with httpx.AsyncClient() as c:
        await c.post(f"{TELEGRAM_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": texto,
            "reply_markup": teclado
        })

async def responder_callback(callback_id, texto=""):
    async with httpx.AsyncClient() as c:
        await c.post(f"{TELEGRAM_URL}/answerCallbackQuery", json={
            "callback_query_id": callback_id,
            "text": texto
        })

async def editar_mensaje(chat_id, message_id, texto, botones=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": texto}
    if botones:
        payload["reply_markup"] = {"inline_keyboard": botones}
    async with httpx.AsyncClient() as c:
        await c.post(f"{TELEGRAM_URL}/editMessageText", json=payload)

def get_perfil(telefono):
    try:
        data = sb.table("usuarios").select("*").eq("telefono", telefono).execute().data
        if data:
            return data[0]
        return {"moneda_preferida": "PEN", "objetivo_ahorro_pct": 20, "dia_pago": 1, "ingreso_mensual": 0}
    except:
        return {"moneda_preferida": "PEN", "objetivo_ahorro_pct": 20, "dia_pago": 1, "ingreso_mensual": 0}

def registrar_usuario(telefono):
    try:
        existe = sb.table("usuarios").select("telefono").eq("telefono", telefono).execute()
        if not existe.data:
            sb.table("usuarios").insert({
                "telefono": telefono,
                "moneda_preferida": "PEN",
                "reporte_diario": False,
                "reporte_semanal": True,
                "reporte_mensual": True,
                "activo": True,
                "perfil_completo": False,
                "objetivo_ahorro_pct": 20,
                "dia_pago": 1,
                "ingreso_mensual": 0
            }).execute()
    except Exception as e:
        print("Error registrando usuario:", e)

def convertir_a_moneda_usuario(monto_pen, moneda_usuario):
    tasa = MONEDAS.get(moneda_usuario, {}).get("tasa", 1.0)
    return round(monto_pen * tasa, 2)

def convertir_a_pen(monto, moneda):
    moneda = moneda.upper()
    if moneda == "PEN":
        return monto
    tasa = MONEDAS.get(moneda, {}).get("tasa", 1.0)
    return round(monto / tasa, 2) if tasa > 0 else monto

def calcular_meses_hasta(fecha_str):
    try:
        meses_map = {
            "enero":1,"febrero":2,"marzo":3,"abril":4,
            "mayo":5,"junio":6,"julio":7,"agosto":8,
            "septiembre":9,"octubre":10,"noviembre":11,"diciembre":12
        }
        hoy = date.today()
        for nombre, num in meses_map.items():
            if nombre in fecha_str.lower():
                año = hoy.year if num >= hoy.month else hoy.year + 1
                meses = (año - hoy.year) * 12 + (num - hoy.month)
                return max(1, meses), f"{nombre.capitalize()} {año}"
        if "mes" in fecha_str.lower():
            import re
            nums = re.findall(r'\d+', fecha_str)
            if nums:
                return int(nums[0]), f"{nums[0]} meses"
        return 3, "3 meses"
    except:
        return 3, "3 meses"

def analizar(texto, moneda_usuario="PEN"):
    try:
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": f"""Eres Aibi, analiza el mensaje y responde SOLO JSON sin texto extra.
La moneda preferida del usuario es {moneda_usuario}. Si no especifica moneda, asume {moneda_usuario}.

Acciones posibles:
- Gasto/ingreso: {{"accion":"registrar","tipo":"gasto" o "ingreso","monto":numero,"moneda":"{moneda_usuario}" o la que mencione,"categoria":"Comida" o "Transporte" o "Salud" o "Entretenimiento" o "Trabajo" o "Ahorro" o "Educacion" o "Hogar" o "Ropa" o "Otro","descripcion":"texto corto","nota":"nota adicional o null","compartido":false,"num_personas":1,"es_financiero":true}}
- Dividir gasto: {{"accion":"registrar","tipo":"gasto","monto":numero,"moneda":"{moneda_usuario}","categoria":"Otro","descripcion":"texto","compartido":true,"num_personas":numero,"es_financiero":true}}
- Consultar saldo: {{"accion":"consultar","es_financiero":true}}
- Comparar periodos: {{"accion":"comparar","periodo":"semana" o "mes","es_financiero":true}}
- Proyeccion: {{"accion":"proyeccion","es_financiero":true}}
- Editar gasto: {{"accion":"editar","descripcion_buscar":"texto","monto_nuevo":numero,"es_financiero":true}}
- Eliminar gasto: {{"accion":"eliminar","descripcion_buscar":"texto","es_financiero":true}}
- Buscar: {{"accion":"buscar","termino":"texto","es_financiero":true}}
- Consulta avanzada: {{"accion":"consulta_avanzada","filtro":"categoria" o "mayor_gasto","categoria":"nombre si aplica","es_financiero":true}}
- Ver metas: {{"accion":"metas","es_financiero":true}}
- Crear meta: {{"accion":"crear_meta","nombre":"nombre","monto_objetivo":numero,"fecha_limite":"texto fecha","es_financiero":true}}
- Abonar meta: {{"accion":"abonar_meta","nombre_meta":"texto","monto_abono":numero,"es_financiero":true}}
- Ver presupuestos: {{"accion":"ver_presupuestos","es_financiero":true}}
- Crear presupuesto: {{"accion":"crear_presupuesto","categoria":"nombre","monto_limite":numero,"es_financiero":true}}
- Ver deudas: {{"accion":"ver_deudas","es_financiero":true}}
- Registrar deuda: {{"accion":"registrar_deuda","descripcion":"texto","monto_total":numero,"cuota_mensual":numero,"es_financiero":true}}
- Pagar deuda: {{"accion":"pagar_deuda","descripcion_buscar":"texto","monto_pago":numero,"es_financiero":true}}
- Ver recurrentes: {{"accion":"ver_recurrentes","es_financiero":true}}
- Agregar recurrente: {{"accion":"agregar_recurrente","descripcion":"texto","monto":numero,"categoria":"categoria","dia_mes":numero,"es_financiero":true}}
- Configurar reporte: {{"accion":"configurar_reporte","tipo_reporte":"diario" o "semanal" o "mensual","activar":true o false,"es_financiero":true}}
- No financiero: {{"accion":"ninguna","es_financiero":false}}"""},
                {"role": "user", "content": texto}
            ]
        )
        c = r.choices[0].message.content.strip()
        if "```" in c:
            c = c.split("```")[1].replace("json", "")
        return json.loads(c)
    except Exception as e:
        print("Error IA:", e)
        return {"es_financiero": False}

def guardar(telefono, datos, moneda_usuario="PEN"):
    try:
        monto = datos.get("monto", 0)
        moneda = datos.get("moneda", moneda_usuario).upper()
        compartido = datos.get("compartido", False)
        num_personas = datos.get("num_personas", 1)
        monto_original = monto
        monto_pen = convertir_a_pen(monto, moneda)
        if compartido and num_personas > 1:
            monto_pen = round(monto_pen / num_personas, 2)
            monto_original = round(monto / num_personas, 2)
        monto_display = convertir_a_moneda_usuario(monto_pen, moneda_usuario)
        sb.table("transacciones").insert({
            "telefono": telefono,
            "tipo": datos.get("tipo"),
            "monto": monto_pen,
            "monto_original": monto_original,
            "moneda": moneda,
            "categoria": datos.get("categoria"),
            "descripcion": datos.get("descripcion"),
            "nota": datos.get("nota"),
            "compartido": compartido,
            "num_personas": num_personas,
            "fecha": datetime.now(timezone.utc).isoformat()
        }).execute()
        return True, monto_display, moneda_usuario
    except Exception as e:
        print("Error guardando:", e)
        return False, 0, moneda_usuario

def resumen(telefono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        data = sb.table("transacciones").select("*").eq("telefono", telefono).execute().data
        if not data:
            return f"No tienes registros aun.\n\nEmpieza diciendome:\nGaste 10 en menu"
        ing_pen = sum(r["monto"] for r in data if r["tipo"] == "ingreso")
        gas_pen = sum(r["monto"] for r in data if r["tipo"] == "gasto")
        bal_pen = ing_pen - gas_pen
        ing = convertir_a_moneda_usuario(ing_pen, moneda)
        gas = convertir_a_moneda_usuario(gas_pen, moneda)
        bal = convertir_a_moneda_usuario(bal_pen, moneda)
        sim = simbolo(moneda)
        cats = {}
        for r in data:
            if r["tipo"] == "gasto":
                c = r["categoria"] or "Otro"
                cats[c] = cats.get(c, 0) + r["monto"]
        top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        top_txt = "\n".join([f"  {c}: {sim} {convertir_a_moneda_usuario(m, moneda):.0f}" for c, m in top])
        pct = round((gas_pen / ing_pen) * 100) if ing_pen > 0 else 0
        dias = date.today().day
        gasto_diario = convertir_a_moneda_usuario(gas_pen / dias, moneda) if dias > 0 else 0
        proyeccion = gasto_diario * 30
        obj_ahorro = perfil.get("objetivo_ahorro_pct", 20)
        ahorro_real = round((1 - gas_pen/ing_pen) * 100) if ing_pen > 0 else 0
        if pct > 90: consejo = "Alerta: gastas casi todo lo que ganas."
        elif pct > 70: consejo = f"Gastas el {pct}% de tus ingresos."
        else: consejo = f"Excelente! Solo gastas el {pct}% de tus ingresos."
        ahorro_txt = f"Ahorro real: {ahorro_real}% (meta: {obj_ahorro}%)"
        signo = "+" if bal >= 0 else ""
        return f"""Tu resumen Aibi:

Ingresos: {sim} {ing:.0f}
Gastos:   {sim} {gas:.0f}
Balance:  {signo}{sim} {bal:.0f}

Top gastos:
{top_txt}

Gasto diario: {sim} {gasto_diario:.0f}
Proyeccion/mes: {sim} {proyeccion:.0f}
{ahorro_txt}

{consejo}{tip()}"""
    except Exception as e:
        print("Error resumen:", e)
        return "Error consultando tus datos."

def comparar(telefono, periodo):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        data = sb.table("transacciones").select("*").eq("telefono", telefono).eq("tipo", "gasto").execute().data
        if not data:
            return "No tienes gastos registrados aun."
        hoy = date.today()
        if periodo == "semana":
            from datetime import timedelta
            inicio_esta = hoy - timedelta(days=hoy.weekday())
            inicio_anterior = inicio_esta - timedelta(days=7)
            esta_pen = sum(r["monto"] for r in data if r["fecha"] and r["fecha"][:10] >= str(inicio_esta))
            anterior_pen = sum(r["monto"] for r in data if r["fecha"] and str(inicio_anterior) <= r["fecha"][:10] < str(inicio_esta))
            esta = convertir_a_moneda_usuario(esta_pen, moneda)
            anterior = convertir_a_moneda_usuario(anterior_pen, moneda)
            diff = esta - anterior
            signo = "+" if diff > 0 else ""
            return f"""Comparacion semanal:

Esta semana:    {sim} {esta:.0f}
Semana pasada:  {sim} {anterior:.0f}
Diferencia:     {signo}{sim} {diff:.0f}

{"Gastas mas que la semana pasada. Cuidado!" if diff > 0 else "Gastas menos que la semana pasada. Excelente!"}{tip()}"""
        else:
            este_pen = sum(r["monto"] for r in data if r["fecha"] and r["fecha"][5:7] == str(hoy.month).zfill(2))
            mes_ant = hoy.month - 1 if hoy.month > 1 else 12
            año_ant = hoy.year if hoy.month > 1 else hoy.year - 1
            anterior_pen = sum(r["monto"] for r in data if r["fecha"] and r["fecha"][5:7] == str(mes_ant).zfill(2) and r["fecha"][:4] == str(año_ant))
            este = convertir_a_moneda_usuario(este_pen, moneda)
            anterior = convertir_a_moneda_usuario(anterior_pen, moneda)
            diff = este - anterior
            signo = "+" if diff > 0 else ""
            return f"""Comparacion mensual:

Este mes:       {sim} {este:.0f}
Mes anterior:   {sim} {anterior:.0f}
Diferencia:     {signo}{sim} {diff:.0f}

{"Van en aumento. Revisa tus gastos!" if diff > 0 else "Vas mejorando mes a mes!"}{tip()}"""
    except Exception as e:
        return "Error al comparar periodos."

def proyeccion(telefono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        data = sb.table("transacciones").select("*").eq("telefono", telefono).execute().data
        if not data:
            return "No tienes datos suficientes para proyectar."
        ing_pen = sum(r["monto"] for r in data if r["tipo"] == "ingreso")
        gas_pen = sum(r["monto"] for r in data if r["tipo"] == "gasto")
        dias = date.today().day
        gasto_diario_pen = gas_pen / dias if dias > 0 else 0
        bal_pen = ing_pen - gas_pen
        bal = convertir_a_moneda_usuario(bal_pen, moneda)
        gasto_diario = convertir_a_moneda_usuario(gasto_diario_pen, moneda)
        gas_proyectado = gasto_diario * 30
        dias_restantes = round(bal_pen / gasto_diario_pen) if gasto_diario_pen > 0 else 999
        if dias_restantes < 0:
            estado = "Ya estas en numeros rojos!"
        elif dias_restantes < 7:
            estado = f"Alerta: te quedan ~{dias_restantes} dias de dinero."
        elif dias_restantes < 15:
            estado = f"Cuidado: te quedan ~{dias_restantes} dias."
        else:
            estado = f"Vas bien, tienes para ~{dias_restantes} dias mas."
        gasto_reducido = convertir_a_moneda_usuario(gasto_diario_pen * 0.8, moneda)
        return f"""Proyeccion financiera Aibi:

Balance actual:       {sim} {bal:.0f}
Gasto diario:         {sim} {gasto_diario:.0f}
Proyeccion mensual:   {sim} {gas_proyectado:.0f}

{estado}

Si reduces tu gasto a {sim} {gasto_reducido:.0f}/dia (-20%)
tendras para {round(bal_pen / (gasto_diario_pen * 0.8))} dias mas.{tip()}"""
    except Exception as e:
        return "Error calculando proyeccion."

def buscar(telefono, termino):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        data = sb.table("transacciones").select("*").eq("telefono", telefono).ilike("descripcion", f"%{termino}%").order("id", desc=True).limit(10).execute().data
        if not data:
            return f"No encontre registros con '{termino}'."
        total_pen = sum(r["monto"] for r in data)
        total = convertir_a_moneda_usuario(total_pen, moneda)
        resultado = f"Encontre {len(data)} registros con '{termino}':\n\n"
        for r in data[:5]:
            emoji = "↑" if r["tipo"] == "ingreso" else "↓"
            fecha = r["fecha"][:10] if r["fecha"] else "Sin fecha"
            monto_display = convertir_a_moneda_usuario(r["monto"], moneda)
            resultado += f"{emoji} {r['descripcion']} - {sim} {monto_display:.0f} ({fecha})\n"
            if r.get("nota"):
                resultado += f"   Nota: {r['nota']}\n"
        if len(data) > 5:
            resultado += f"\n...y {len(data)-5} mas."
        resultado += f"\nTotal: {sim} {total:.0f}"
        return resultado
    except Exception as e:
        return "Error buscando en tu historial."

def editar(telefono, descripcion_buscar, monto_nuevo):
    try:
        result = sb.table("transacciones").select("*").eq("telefono", telefono).ilike("descripcion", f"%{descripcion_buscar}%").order("id", desc=True).limit(1).execute()
        if not result.data:
            return f"No encontre ningun gasto con '{descripcion_buscar}'."
        registro = result.data[0]
        sb.table("transacciones").update({"monto": monto_nuevo}).eq("id", registro["id"]).execute()
        return f"Actualice '{registro['descripcion']}' de S/ {registro['monto']} a S/ {monto_nuevo}"
    except Exception as e:
        return "Error al editar el gasto."

def eliminar(telefono, descripcion_buscar):
    try:
        result = sb.table("transacciones").select("*").eq("telefono", telefono).ilike("descripcion", f"%{descripcion_buscar}%").order("id", desc=True).limit(1).execute()
        if not result.data:
            return f"No encontre ningun gasto con '{descripcion_buscar}'."
        registro = result.data[0]
        sb.table("transacciones").delete().eq("id", registro["id"]).execute()
        return f"Elimine '{registro['descripcion']}' de S/ {registro['monto']}."
    except Exception as e:
        return "Error al eliminar el gasto."

def consulta_avanzada(telefono, filtro, categoria=None):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        query = sb.table("transacciones").select("*").eq("telefono", telefono).eq("tipo", "gasto")
        if categoria:
            query = query.eq("categoria", categoria)
        data = query.execute().data
        if not data:
            return "No encontre gastos con ese criterio."
        if filtro == "mayor_gasto":
            mayor = max(data, key=lambda x: x["monto"])
            monto_display = convertir_a_moneda_usuario(mayor["monto"], moneda)
            return f"Tu mayor gasto:\n\n{mayor['descripcion']}\n{sim} {monto_display:.0f}\n{mayor['categoria']}"
        if filtro == "categoria" and categoria:
            total_pen = sum(r["monto"] for r in data)
            total = convertir_a_moneda_usuario(total_pen, moneda)
            return f"Total en {categoria}:\n\n{sim} {total:.0f}\n{len(data)} transacciones{tip()}"
        total_pen = sum(r["monto"] for r in data)
        total = convertir_a_moneda_usuario(total_pen, moneda)
        return f"Total: {sim} {total:.0f} en {len(data)} transacciones."
    except Exception as e:
        return "Error en la consulta."

def ver_metas(telefono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        data = sb.table("metas").select("*").eq("telefono", telefono).eq("completada", False).execute().data
        if not data:
            return "No tienes metas activas.\n\nCrea una asi:\nMeta: Viaje a Cusco S/500 para junio"
        resp = "Tus metas de ahorro:\n"
        for m in data:
            obj = convertir_a_moneda_usuario(m["monto_objetivo"], moneda)
            act = convertir_a_moneda_usuario(m["monto_actual"], moneda)
            fal = convertir_a_moneda_usuario(m["monto_objetivo"] - m["monto_actual"], moneda)
            pct = round((m["monto_actual"] / m["monto_objetivo"]) * 100) if m["monto_objetivo"] > 0 else 0
            barra = ("=" * (pct // 10)) + ("-" * (10 - pct // 10))
            resp += f"\n{m['nombre']}\n[{barra}] {pct}%\n{sim} {act:.0f} de {sim} {obj:.0f}\nFaltan: {sim} {fal:.0f}"
            if m.get("monto_mensual_requerido"):
                mensual = convertir_a_moneda_usuario(m["monto_mensual_requerido"], moneda)
                resp += f"\nAhorra {sim} {mensual:.0f}/mes para lograrlo"
            if m.get("fecha_limite"):
                resp += f"\nFecha: {m['fecha_limite']}"
            resp += "\n"
        return resp + tip()
    except Exception as e:
        return "Error consultando metas."

def crear_meta(telefono, nombre, monto_objetivo, fecha_limite_txt=None):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        monto_pen = convertir_a_pen(monto_objetivo, moneda)
        ing_data = sb.table("transacciones").select("monto").eq("telefono", telefono).eq("tipo", "ingreso").execute().data
        ingreso_mensual_pen = sum(r["monto"] for r in ing_data) if ing_data else 0
        meses, fecha_str = calcular_meses_hasta(fecha_limite_txt) if fecha_limite_txt else (3, "3 meses")
        monto_mensual_pen = round(monto_pen / meses, 2) if meses > 0 else monto_pen
        pct_ingreso = round((monto_mensual_pen / ingreso_mensual_pen) * 100) if ingreso_mensual_pen > 0 else 0
        sb.table("metas").insert({
            "telefono": telefono,
            "nombre": nombre,
            "monto_objetivo": monto_pen,
            "monto_actual": 0,
            "completada": False,
            "fecha_limite": fecha_str,
            "monto_mensual_requerido": monto_mensual_pen,
            "fecha_creacion": str(date.today())
        }).execute()
        mensual_display = convertir_a_moneda_usuario(monto_mensual_pen, moneda)
        obj_display = convertir_a_moneda_usuario(monto_pen, moneda)
        resp = f"Meta creada!\n\n{nombre}\nObjetivo: {sim} {obj_display:.0f}\nFecha: {fecha_str}\n\nPlan de ahorro:\nNecesitas {sim} {mensual_display:.0f}/mes"
        if ingreso_mensual_pen > 0:
            resp += f"\nEso es el {pct_ingreso}% de tus ingresos"
            if pct_ingreso > 50:
                resp += f"\n\nMeta ambiciosa. Revisa donde puedes recortar gastos para lograrlo."
            elif pct_ingreso > 30:
                resp += f"\n\nAlcanzable reduciendo algunos gastos variables."
            else:
                resp += f"\n\nExcelente! Meta muy alcanzable con tu nivel de ingresos."
        resp += f"\n\nPara abonar escribe:\nAbone [monto] a {nombre}"
        return resp
    except Exception as e:
        print("Error creando meta:", e)
        return "Error creando la meta."

def abonar_meta(telefono, nombre_meta, monto_abono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        monto_pen = convertir_a_pen(monto_abono, moneda)
        metas = sb.table("metas").select("*").eq("telefono", telefono).eq("completada", False).ilike("nombre", f"%{nombre_meta}%").execute().data
        if not metas:
            return f"No encontre la meta '{nombre_meta}'.\nEscribe 'Mis metas' para verlas."
        meta = metas[0]
        nuevo_total = meta["monto_actual"] + monto_pen
        completada = nuevo_total >= meta["monto_objetivo"]
        sb.table("metas").update({"monto_actual": nuevo_total, "completada": completada}).eq("id", meta["id"]).execute()
        pct = round((nuevo_total / meta["monto_objetivo"]) * 100)
        barra = ("=" * min(pct // 10, 10)) + ("-" * max(10 - pct // 10, 0))
        act_display = convertir_a_moneda_usuario(nuevo_total, moneda)
        obj_display = convertir_a_moneda_usuario(meta["monto_objetivo"], moneda)
        fal_display = convertir_a_moneda_usuario(meta["monto_objetivo"] - nuevo_total, moneda)
        if completada:
            return f"FELICITACIONES! Lograste tu meta!\n\n{meta['nombre']}\n[==========] 100%\n{sim} {obj_display:.0f} completados!\n\nEres increible! Meta lograda!"
        return f"Abono registrado!\n\n{meta['nombre']}\n[{barra}] {pct}%\n{sim} {act_display:.0f} de {sim} {obj_display:.0f}\nFaltan: {sim} {fal_display:.0f}\n\n{'Ya casi! Sigue asi!' if pct > 80 else 'Buen avance! Continua!'}{tip()}"
    except Exception as e:
        print("Error abonando:", e)
        return "Error al abonar a la meta."

def crear_presupuesto(telefono, categoria, monto_limite):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        monto_pen = convertir_a_pen(monto_limite, moneda)
        hoy = date.today()
        existente = sb.table("presupuestos").select("*").eq("telefono", telefono).eq("categoria", categoria).eq("mes", hoy.month).eq("año", hoy.year).execute().data
        if existente:
            sb.table("presupuestos").update({"monto_limite": monto_pen}).eq("id", existente[0]["id"]).execute()
            return f"Presupuesto actualizado!\n\n{categoria}: {sim} {monto_limite:.0f}/mes"
        sb.table("presupuestos").insert({
            "telefono": telefono, "categoria": categoria,
            "monto_limite": monto_pen, "mes": hoy.month, "año": hoy.year
        }).execute()
        return f"Presupuesto creado!\n\n{categoria}: {sim} {monto_limite:.0f}/mes\nTe aviso cuando llegues al 80%."
    except Exception as e:
        return "Error creando presupuesto."

def ver_presupuestos(telefono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        hoy = date.today()
        presupuestos = sb.table("presupuestos").select("*").eq("telefono", telefono).eq("mes", hoy.month).eq("año", hoy.year).execute().data
        if not presupuestos:
            return "No tienes presupuestos este mes.\n\nCrea uno:\nPresupuesto Comida S/300"
        gastos = sb.table("transacciones").select("*").eq("telefono", telefono).eq("tipo", "gasto").execute().data
        resp = "Presupuestos de este mes:\n"
        for p in presupuestos:
            gastado_pen = sum(r["monto"] for r in gastos if r["categoria"] == p["categoria"] and r["fecha"] and r["fecha"][5:7] == str(hoy.month).zfill(2))
            gastado = convertir_a_moneda_usuario(gastado_pen, moneda)
            limite = convertir_a_moneda_usuario(p["monto_limite"], moneda)
            pct = round((gastado_pen / p["monto_limite"]) * 100) if p["monto_limite"] > 0 else 0
            restante = limite - gastado
            barra = ("=" * min(pct // 10, 10)) + ("-" * max(10 - pct // 10, 0))
            estado = "SUPERADO!" if pct >= 100 else "Casi al limite!" if pct >= 80 else "OK"
            resp += f"\n{p['categoria']}\n[{barra}] {pct}%\n{sim} {gastado:.0f} de {sim} {limite:.0f} - {estado}\n"
        return resp
    except Exception as e:
        return "Error viendo presupuestos."

def verificar_presupuesto(telefono, categoria, monto_nuevo_pen):
    try:
        hoy = date.today()
        p = sb.table("presupuestos").select("*").eq("telefono", telefono).eq("categoria", categoria).eq("mes", hoy.month).eq("año", hoy.year).execute().data
        if not p:
            return None
        gastos = sb.table("transacciones").select("monto").eq("telefono", telefono).eq("tipo", "gasto").eq("categoria", categoria).execute().data
        gastado = sum(r["monto"] for r in gastos) + monto_nuevo_pen
        pct = round((gastado / p[0]["monto_limite"]) * 100)
        if pct >= 100:
            return f"\nAlerta: Superaste tu presupuesto de {categoria}!"
        elif pct >= 80:
            return f"\nOjo: Llevas el {pct}% de tu presupuesto de {categoria}."
        return None
    except:
        return None

def registrar_deuda(telefono, descripcion, monto_total, cuota_mensual):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        monto_pen = convertir_a_pen(monto_total, moneda)
        cuota_pen = convertir_a_pen(cuota_mensual, moneda)
        sb.table("deudas").insert({
            "telefono": telefono, "descripcion": descripcion,
            "monto_total": monto_pen, "monto_pagado": 0,
            "cuota_mensual": cuota_pen, "fecha_inicio": str(date.today()),
            "completada": False
        }).execute()
        meses = round(monto_pen / cuota_pen) if cuota_pen > 0 else 0
        return f"Deuda registrada!\n\n{descripcion}\nTotal: {sim} {monto_total:.0f}\nCuota: {sim} {cuota_mensual:.0f}/mes\nTiempo: ~{meses} meses"
    except Exception as e:
        return "Error registrando deuda."

def ver_deudas(telefono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        deudas = sb.table("deudas").select("*").eq("telefono", telefono).eq("completada", False).execute().data
        if not deudas:
            return "No tienes deudas registradas.\n\nPara registrar:\nDebo S/500 al banco cuota S/100"
        total_pen = sum(d["monto_total"] - d["monto_pagado"] for d in deudas)
        total = convertir_a_moneda_usuario(total_pen, moneda)
        resp = f"Tus deudas activas:\nTotal pendiente: {sim} {total:.0f}\n"
        for d in deudas:
            pendiente_pen = d["monto_total"] - d["monto_pagado"]
            pendiente = convertir_a_moneda_usuario(pendiente_pen, moneda)
            cuota = convertir_a_moneda_usuario(d["cuota_mensual"], moneda)
            pct = round((d["monto_pagado"] / d["monto_total"]) * 100) if d["monto_total"] > 0 else 0
            meses = round(pendiente_pen / d["cuota_mensual"]) if d["cuota_mensual"] > 0 else 0
            barra = ("=" * (pct // 10)) + ("-" * (10 - pct // 10))
            resp += f"\n{d['descripcion']}\n[{barra}] {pct}% pagado\nPendiente: {sim} {pendiente:.0f}\nCuota: {sim} {cuota:.0f}/mes (~{meses} meses)\n"
        return resp
    except Exception as e:
        return "Error viendo deudas."

def pagar_deuda(telefono, descripcion_buscar, monto_pago):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        monto_pen = convertir_a_pen(monto_pago, moneda)
        deudas = sb.table("deudas").select("*").eq("telefono", telefono).eq("completada", False).ilike("descripcion", f"%{descripcion_buscar}%").execute().data
        if not deudas:
            return f"No encontre deuda con '{descripcion_buscar}'."
        deuda = deudas[0]
        nuevo_pagado = deuda["monto_pagado"] + monto_pen
        completada = nuevo_pagado >= deuda["monto_total"]
        sb.table("deudas").update({"monto_pagado": nuevo_pagado, "completada": completada}).eq("id", deuda["id"]).execute()
        if completada:
            return f"DEUDA COMPLETADA!\n\n{deuda['descripcion']}\nFelicitaciones! Una deuda menos!"
        pendiente = convertir_a_moneda_usuario(deuda["monto_total"] - nuevo_pagado, moneda)
        pct = round((nuevo_pagado / deuda["monto_total"]) * 100)
        return f"Pago registrado!\n\n{deuda['descripcion']}\nPendiente: {sim} {pendiente:.0f}\nProgreso: {pct}%"
    except Exception as e:
        return "Error registrando pago."

def agregar_recurrente(telefono, descripcion, monto, categoria, dia_mes):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        monto_pen = convertir_a_pen(monto, moneda)
        sb.table("recurrentes").insert({
            "telefono": telefono, "descripcion": descripcion,
            "monto": monto_pen, "categoria": categoria,
            "dia_mes": dia_mes, "activo": True
        }).execute()
        return f"Gasto fijo agregado!\n\n{descripcion}\n{sim} {monto:.0f}/mes - Dia {dia_mes}"
    except Exception as e:
        return "Error agregando gasto recurrente."

def ver_recurrentes(telefono):
    try:
        perfil = get_perfil(telefono)
        moneda = perfil.get("moneda_preferida", "PEN")
        sim = simbolo(moneda)
        data = sb.table("recurrentes").select("*").eq("telefono", telefono).eq("activo", True).execute().data
        if not data:
            return "No tienes gastos fijos.\n\nAgrega uno:\nRecurrente: Netflix S/35 dia 15"
        total_pen = sum(r["monto"] for r in data)
        total = convertir_a_moneda_usuario(total_pen, moneda)
        resp = f"Gastos fijos mensuales:\nTotal: {sim} {total:.0f}/mes\n"
        for r in data:
            monto_display = convertir_a_moneda_usuario(r["monto"], moneda)
            resp += f"\n{r['descripcion']}\n{sim} {monto_display:.0f} - Dia {r['dia_mes']}\n"
        return resp
    except Exception as e:
        return "Error viendo recurrentes."

def configurar_reporte(telefono, tipo_reporte, activar):
    try:
        campo = f"reporte_{tipo_reporte}"
        sb.table("usuarios").update({campo: activar}).eq("telefono", telefono).execute()
        estado = "activado" if activar else "desactivado"
        return f"Reporte {tipo_reporte} {estado}."
    except Exception as e:
        return "Error actualizando configuracion."

async def mostrar_menu_config(chat_id, perfil):
    moneda = perfil.get("moneda_preferida", "PEN")
    obj = perfil.get("objetivo_ahorro_pct", 20)
    dia = perfil.get("dia_pago", 1)
    rep_d = "ON" if perfil.get("reporte_diario") else "OFF"
    rep_s = "ON" if perfil.get("reporte_semanal") else "OFF"
    rep_m = "ON" if perfil.get("reporte_mensual") else "OFF"
    texto = f"""Configuracion de Aibi:

Moneda: {moneda} {simbolo(moneda)}
Meta de ahorro: {obj}%
Dia de pago: {dia}
Reportes: Diario {rep_d} | Semanal {rep_s} | Mensual {rep_m}

Selecciona que quieres cambiar:"""
    botones = [
        [{"text": "💰 Cambiar moneda", "callback_data": "cfg_moneda"}],
        [{"text": f"🎯 Meta ahorro ({obj}%)", "callback_data": "cfg_ahorro"}],
        [{"text": f"📅 Dia de pago (dia {dia})", "callback_data": "cfg_dia_pago"}],
        [
            {"text": f"📊 Diario {rep_d}", "callback_data": "cfg_rep_diario"},
            {"text": f"📈 Semanal {rep_s}", "callback_data": "cfg_rep_semanal"},
            {"text": f"📉 Mensual {rep_m}", "callback_data": "cfg_rep_mensual"},
        ],
        [{"text": "❌ Cerrar", "callback_data": "cfg_cerrar"}]
    ]
    await enviar_botones(chat_id, texto, botones)

async def mostrar_menu_monedas(chat_id, message_id):
    texto = "Selecciona tu moneda principal:"
    botones = [
        [{"text": "🇵🇪 Soles (PEN)", "callback_data": "moneda_PEN"}, {"text": "🇺🇸 Dolares (USD)", "callback_data": "moneda_USD"}],
        [{"text": "🇪🇺 Euros (EUR)", "callback_data": "moneda_EUR"}, {"text": "🇨🇴 Pesos CO (COP)", "callback_data": "moneda_COP"}],
        [{"text": "🇲🇽 Pesos MX (MXN)", "callback_data": "moneda_MXN"}, {"text": "🇨🇱 Pesos CL (CLP)", "callback_data": "moneda_CLP"}],
        [{"text": "🇧🇷 Reales (BRL)", "callback_data": "moneda_BRL"}],
        [{"text": "↩ Volver", "callback_data": "cfg_volver"}]
    ]
    await editar_mensaje(chat_id, message_id, texto, botones)

async def mostrar_menu_ahorro(chat_id, message_id):
    texto = "Selecciona tu meta de ahorro mensual:"
    botones = [
        [{"text": "10%", "callback_data": "ahorro_10"}, {"text": "15%", "callback_data": "ahorro_15"}, {"text": "20%", "callback_data": "ahorro_20"}],
        [{"text": "25%", "callback_data": "ahorro_25"}, {"text": "30%", "callback_data": "ahorro_30"}, {"text": "40%", "callback_data": "ahorro_40"}],
        [{"text": "↩ Volver", "callback_data": "cfg_volver"}]
    ]
    await editar_mensaje(chat_id, message_id, texto, botones)

async def mostrar_menu_dia_pago(chat_id, message_id):
    texto = "Selecciona tu dia de pago/cobro del mes:"
    botones = [
        [{"text": f"Dia {d}", "callback_data": f"dia_{d}"} for d in [1, 5, 10]],
        [{"text": f"Dia {d}", "callback_data": f"dia_{d}"} for d in [15, 20, 25]],
        [{"text": "Dia 30", "callback_data": "dia_30"}, {"text": "↩ Volver", "callback_data": "cfg_volver"}]
    ]
    await editar_mensaje(chat_id, message_id, texto, botones)

async def procesar_callback(chat_id, message_id, callback_id, data_cb, telefono):
    await responder_callback(callback_id)
    perfil = get_perfil(telefono)

    if data_cb == "cfg_cerrar":
        await editar_mensaje(chat_id, message_id, "Configuracion cerrada. Escribe 'configuracion' para volver.")
        return

    if data_cb == "cfg_volver":
        await mostrar_menu_config(chat_id, perfil)
        return

    if data_cb == "cfg_moneda":
        await mostrar_menu_monedas(chat_id, message_id)
        return

    if data_cb == "cfg_ahorro":
        await mostrar_menu_ahorro(chat_id, message_id)
        return

    if data_cb == "cfg_dia_pago":
        await mostrar_menu_dia_pago(chat_id, message_id)
        return

    if data_cb.startswith("moneda_"):
        nueva_moneda = data_cb.replace("moneda_", "")
        sb.table("usuarios").update({"moneda_preferida": nueva_moneda}).eq("telefono", telefono).execute()
        info = MONEDAS.get(nueva_moneda, {})
        await editar_mensaje(chat_id, message_id,
            f"Moneda actualizada!\n\n{info.get('nombre', nueva_moneda)} {info.get('simbolo', '')}\n\nAhora todos tus montos se mostraran en {nueva_moneda}.",
            [[{"text": "↩ Volver a configuracion", "callback_data": "cfg_volver"}]]
        )
        return

    if data_cb.startswith("ahorro_"):
        pct = int(data_cb.replace("ahorro_", ""))
        sb.table("usuarios").update({"objetivo_ahorro_pct": pct}).eq("telefono", telefono).execute()
        await editar_mensaje(chat_id, message_id,
            f"Meta de ahorro actualizada!\n\nAhora tu meta es ahorrar el {pct}% de tus ingresos cada mes.\n\nAibi te informara si estas logrando esta meta.",
            [[{"text": "↩ Volver a configuracion", "callback_data": "cfg_volver"}]]
        )
        return

    if data_cb.startswith("dia_"):
        dia = int(data_cb.replace("dia_", ""))
        sb.table("usuarios").update({"dia_pago": dia}).eq("telefono", telefono).execute()
        await editar_mensaje(chat_id, message_id,
            f"Dia de pago actualizado!\n\nAibi recordara que el dia {dia} de cada mes es tu dia de cobro/pago.",
            [[{"text": "↩ Volver a configuracion", "callback_data": "cfg_volver"}]]
        )
        return

    if data_cb in ["cfg_rep_diario", "cfg_rep_semanal", "cfg_rep_mensual"]:
        tipo = data_cb.replace("cfg_rep_", "")
        campo = f"reporte_{tipo}"
        actual = perfil.get(campo, False)
        nuevo = not actual
        sb.table("usuarios").update({campo: nuevo}).eq("telefono", telefono).execute()
        estado = "activado" if nuevo else "desactivado"
        perfil[campo] = nuevo
        await mostrar_menu_config(chat_id, perfil)
        return

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        message_id = cb["message"]["message_id"]
        callback_id = cb["id"]
        data_cb = cb.get("data", "")
        telefono = str(chat_id)
        registrar_usuario(telefono)
        await procesar_callback(chat_id, message_id, callback_id, data_cb, telefono)
        return {"ok": True}

    if "message" not in data:
        return {"ok": True}

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    texto = msg.get("text", "")
    telefono = str(chat_id)
    print(f"Mensaje Telegram {chat_id}: {texto}")
    registrar_usuario(telefono)
    perfil = get_perfil(telefono)
    moneda_usuario = perfil.get("moneda_preferida", "PEN")

    if any(s in texto.lower() for s in ["configuracion", "configuración", "config", "ajustes", "settings"]):
        await mostrar_menu_config(chat_id, perfil)
        return {"ok": True}

    datos = analizar(texto, moneda_usuario)
    print("Analisis:", datos)

    if not datos.get("es_financiero"):
        es_saludo = any(s in texto.lower() for s in [
            "hola","hi","hey","buenas","buen dia","buenas tardes",
            "buenas noches","saludos","que tal","como estas","hello","start","/start"
        ])
        if es_saludo:
            sim = simbolo(moneda_usuario)
            await enviar(chat_id,
                f"Hola! Soy Aibi, tu asesor financiero personal.\n\n"
                f"Tu moneda: {moneda_usuario} {sim}\n\n"
                f"Puedes decirme:\n"
                f"Gaste 15 en almuerzo\n"
                f"Ingrese 500 de sueldo\n"
                f"Cuanto tengo?\n"
                f"Meta: Viaje S/500 para junio\n"
                f"Abone 50 a mi viaje\n"
                f"Presupuesto Comida 300\n"
                f"Debo 500 al banco cuota 100\n"
                f"Comparar esta semana\n"
                f"Proyeccion financiera\n"
                f"Buscar pizza\n"
                f"Configuracion\n\n"
                f"En que te ayudo hoy?" + tip()
            )
        else:
            await enviar(chat_id, "No entendi. Escribe Hola para ver que puedo hacer o Configuracion para ajustar tus preferencias." + tip())
        return {"ok": True}

    accion = datos.get("accion")

    if accion == "registrar":
        guardado, monto_display, mon = guardar(telefono, datos, moneda_usuario)
        tipo = datos.get("tipo", "gasto")
        cat = datos.get("categoria", "Otro")
        desc = datos.get("descripcion", texto)
        nota = datos.get("nota")
        compartido = datos.get("compartido", False)
        num_personas = datos.get("num_personas", 1)
        sim = simbolo(mon)
        emoji = "Gasto" if tipo == "gasto" else "Ingreso"
        msg_resp = f"{emoji} registrado!\n\n{desc}\n{sim} {monto_display:.0f}\n{cat}"
        if nota:
            msg_resp += f"\nNota: {nota}"
        if compartido and num_personas > 1:
            msg_resp += f"\nDividido entre {num_personas} personas"
        if tipo == "gasto":
            monto_pen = convertir_a_pen(datos.get("monto", 0), datos.get("moneda", moneda_usuario))
            alerta = verificar_presupuesto(telefono, cat, monto_pen)
            if alerta:
                msg_resp += alerta
        if random.random() > 0.6:
            msg_resp += tip()
        await enviar(chat_id, msg_resp)

    elif accion == "consultar":
        await enviar(chat_id, resumen(telefono))
    elif accion == "comparar":
        await enviar(chat_id, comparar(telefono, datos.get("periodo", "semana")))
    elif accion == "proyeccion":
        await enviar(chat_id, proyeccion(telefono))
    elif accion == "buscar":
        await enviar(chat_id, buscar(telefono, datos.get("termino", "")))
    elif accion == "editar":
        await enviar(chat_id, editar(telefono, datos.get("descripcion_buscar", ""), datos.get("monto_nuevo", 0)))
    elif accion == "eliminar":
        await enviar(chat_id, eliminar(telefono, datos.get("descripcion_buscar", "")))
    elif accion == "consulta_avanzada":
        await enviar(chat_id, consulta_avanzada(telefono, datos.get("filtro", ""), datos.get("categoria")))
    elif accion == "metas":
        await enviar(chat_id, ver_metas(telefono))
    elif accion == "crear_meta":
        await enviar(chat_id, crear_meta(telefono, datos.get("nombre", "Meta"), datos.get("monto_objetivo", 0), datos.get("fecha_limite")))
    elif accion == "abonar_meta":
        await enviar(chat_id, abonar_meta(telefono, datos.get("nombre_meta", ""), datos.get("monto_abono", 0)))
    elif accion == "ver_presupuestos":
        await enviar(chat_id, ver_presupuestos(telefono))
    elif accion == "crear_presupuesto":
        await enviar(chat_id, crear_presupuesto(telefono, datos.get("categoria", "Otro"), datos.get("monto_limite", 0)))
    elif accion == "ver_deudas":
        await enviar(chat_id, ver_deudas(telefono))
    elif accion == "registrar_deuda":
        await enviar(chat_id, registrar_deuda(telefono, datos.get("descripcion", "Deuda"), datos.get("monto_total", 0), datos.get("cuota_mensual", 0)))
    elif accion == "pagar_deuda":
        await enviar(chat_id, pagar_deuda(telefono, datos.get("descripcion_buscar", ""), datos.get("monto_pago", 0)))
    elif accion == "ver_recurrentes":
        await enviar(chat_id, ver_recurrentes(telefono))
    elif accion == "agregar_recurrente":
        await enviar(chat_id, agregar_recurrente(telefono, datos.get("descripcion", ""), datos.get("monto", 0), datos.get("categoria", "Otro"), datos.get("dia_mes", 1)))
    elif accion == "configurar_reporte":
        await enviar(chat_id, configurar_reporte(telefono, datos.get("tipo_reporte", ""), datos.get("activar", True)))
    else:
        await enviar(chat_id, "No entendi. Escribe Hola para ver que puedo hacer." + tip())

    return {"ok": True}

@app.get("/")
def inicio():
    return {"aibi": "v2 completo con configuracion y monedas"}
