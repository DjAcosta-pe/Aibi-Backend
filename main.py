from fastapi import FastAPI, Form
from fastapi.responses import Response
from groq import Groq
from supabase import create_client
from datetime import datetime, timezone
import json, os, random

app = FastAPI()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
sb = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

TIPS = [
    "Ahorrar el 10% de cada ingreso es el primer paso hacia la libertad financiera.",
    "Regla 50/30/20: 50% necesidades, 30% deseos, 20% ahorro.",
    "Un fondo de emergencia de 3 meses de gastos te protege de cualquier imprevisto.",
    "Los pequenos gastos diarios pueden sumar mas de S/300 al mes sin que te des cuenta.",
    "El mejor momento para ahorrar fue ayer. El segundo mejor momento es hoy.",
    "Pagar tus deudas primero es la mejor inversion que puedes hacer.",
    "Registrar tus gastos diariamente tarda menos de 30 segundos y puede cambiar tu vida.",
]

def xml(msg):
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{msg}</Message></Response>',
        media_type="text/xml"
    )

def tip():
    return f"\n\nTip Aibi: {random.choice(TIPS)}"

def registrar_usuario(telefono):
    try:
        existe = sb.table("usuarios").select("telefono").eq("telefono", telefono).execute()
        if not existe.data:
            sb.table("usuarios").insert({
                "telefono": telefono,
                "reporte_diario": False,
                "reporte_semanal": True,
                "reporte_mensual": True,
                "activo": True
            }).execute()
    except Exception as e:
        print("Error registrando usuario:", e)

def analizar(texto):
    try:
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": """Analiza el mensaje y responde SOLO JSON sin texto extra ni comillas adicionales.

Acciones posibles:
- Si menciona gasto o ingreso: {"accion":"registrar","tipo":"gasto" o "ingreso","monto":numero,"categoria":"Comida" o "Transporte" o "Salud" o "Entretenimiento" o "Trabajo" o "Ahorro" o "Otro","descripcion":"texto corto","es_financiero":true}
- Si pregunta saldo, balance, resumen, cuanto tiene: {"accion":"consultar","es_financiero":true}
- Si quiere editar un gasto: {"accion":"editar","descripcion_buscar":"texto a buscar","monto_nuevo":numero,"es_financiero":true}
- Si quiere eliminar un gasto: {"accion":"eliminar","descripcion_buscar":"texto a buscar","es_financiero":true}
- Si pregunta por categoria especifica o mayor gasto: {"accion":"consulta_avanzada","filtro":"categoria o mayor_gasto","categoria":"nombre si aplica","es_financiero":true}
- Si quiere ver o agregar metas: {"accion":"metas","es_financiero":true}
- Si quiere crear una meta: {"accion":"crear_meta","nombre":"nombre de la meta","monto_objetivo":numero,"es_financiero":true}
- Si quiere activar o desactivar reportes: {"accion":"configurar_reporte","tipo_reporte":"diario o semanal o mensual","activar":true o false,"es_financiero":true}
- Si no es financiero: {"accion":"ninguna","es_financiero":false}"""},
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

def guardar(telefono, datos):
    try:
        sb.table("transacciones").insert({
            "telefono": telefono,
            "tipo": datos.get("tipo"),
            "monto": datos.get("monto"),
            "categoria": datos.get("categoria"),
            "descripcion": datos.get("descripcion"),
            "fecha": datetime.now(timezone.utc).isoformat()
        }).execute()
        return True
    except Exception as e:
        print("Error guardando:", e)
        return False

def editar(telefono, descripcion_buscar, monto_nuevo):
    try:
        result = sb.table("transacciones").select("*").eq("telefono", telefono).ilike("descripcion", f"%{descripcion_buscar}%").order("id", desc=True).limit(1).execute()
        if not result.data:
            return f"No encontre ningun gasto con '{descripcion_buscar}'. Intenta con otra descripcion."
        registro = result.data[0]
        sb.table("transacciones").update({"monto": monto_nuevo}).eq("id", registro["id"]).execute()
        return f"Listo! Actualice '{registro['descripcion']}' de S/ {registro['monto']} a S/ {monto_nuevo}"
    except Exception as e:
        print("Error editando:", e)
        return "Error al editar el gasto."

def eliminar(telefono, descripcion_buscar):
    try:
        result = sb.table("transacciones").select("*").eq("telefono", telefono).ilike("descripcion", f"%{descripcion_buscar}%").order("id", desc=True).limit(1).execute()
        if not result.data:
            return f"No encontre ningun gasto con '{descripcion_buscar}'."
        registro = result.data[0]
        sb.table("transacciones").delete().eq("id", registro["id"]).execute()
        return f"Elimine '{registro['descripcion']}' de S/ {registro['monto']} en {registro['categoria']}."
    except Exception as e:
        print("Error eliminando:", e)
        return "Error al eliminar el gasto."

def resumen(telefono):
    try:
        data = sb.table("transacciones").select("*").eq("telefono", telefono).execute().data
        if not data:
            return "No tienes registros aun.\n\nEmpieza diciendome:\nGaste 10 soles en menu"
        ing = sum(r["monto"] for r in data if r["tipo"] == "ingreso")
        gas = sum(r["monto"] for r in data if r["tipo"] == "gasto")
        bal = ing - gas
        cats = {}
        for r in data:
            if r["tipo"] == "gasto":
                c = r["categoria"] or "Otro"
                cats[c] = cats.get(c, 0) + r["monto"]
        top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        top_txt = "\n".join([f"  {c}: S/ {m:.0f}" for c, m in top])
        pct = round((gas / ing) * 100) if ing > 0 else 0
        if pct > 90: consejo = "Alerta: gastas casi todo lo que ganas."
        elif pct > 70: consejo = f"Gastas el {pct}% de tus ingresos. Meta: bajar al 70%."
        else: consejo = f"Excelente! Solo gastas el {pct}% de tus ingresos."
        signo = "+" if bal >= 0 else ""
        return f"""Tu resumen Aibi:

Ingresos: S/ {ing:.0f}
Gastos:   S/ {gas:.0f}
Balance:  {signo}S/ {bal:.0f}

Top gastos:
{top_txt}

{consejo}{tip()}"""
    except Exception as e:
        print("Error resumen:", e)
        return "Error consultando tus datos."

def consulta_avanzada(telefono, filtro, categoria=None):
    try:
        query = sb.table("transacciones").select("*").eq("telefono", telefono).eq("tipo", "gasto")
        if categoria:
            query = query.eq("categoria", categoria)
        data = query.execute().data
        if not data:
            return "No encontre gastos con ese criterio."
        if filtro == "mayor_gasto":
            mayor = max(data, key=lambda x: x["monto"])
            return f"Tu mayor gasto es:\n\n{mayor['descripcion']}\nS/ {mayor['monto']}\n{mayor['categoria']}\n{mayor['fecha'][:10]}"
        if filtro == "categoria" and categoria:
            total = sum(r["monto"] for r in data)
            return f"Total en {categoria}:\n\nS/ {total:.0f}\n{len(data)} transacciones{tip()}"
        total = sum(r["monto"] for r in data)
        return f"Total encontrado: S/ {total:.0f} en {len(data)} transacciones."
    except Exception as e:
        print("Error consulta avanzada:", e)
        return "Error en la consulta."

def ver_metas(telefono):
    try:
        data = sb.table("metas").select("*").eq("telefono", telefono).eq("completada", False).execute().data
        if not data:
            return "No tienes metas activas.\n\nCrea una asi:\nMeta: Viaje a Cusco S/500"
        resp = "Tus metas de ahorro:\n"
        for m in data:
            pct = round((m["monto_actual"] / m["monto_objetivo"]) * 100) if m["monto_objetivo"] > 0 else 0
            faltan = m["monto_objetivo"] - m["monto_actual"]
            barra = ("=" * (pct // 10)) + ("-" * (10 - pct // 10))
            resp += f"\n{m['nombre']}\n[{barra}] {pct}%\nS/ {m['monto_actual']:.0f} de S/ {m['monto_objetivo']:.0f}\nFaltan: S/ {faltan:.0f}\n"
        return resp + tip()
    except Exception as e:
        print("Error metas:", e)
        return "Error consultando metas."

def crear_meta(telefono, nombre, monto_objetivo):
    try:
        sb.table("metas").insert({
            "telefono": telefono,
            "nombre": nombre,
            "monto_objetivo": monto_objetivo,
            "monto_actual": 0,
            "completada": False
        }).execute()
        return f"Meta creada!\n\n{nombre}\nObjetivo: S/ {monto_objetivo:.0f}\n\nEscribe 'Mis metas' para ver tu progreso."
    except Exception as e:
        print("Error creando meta:", e)
        return "Error creando la meta."

def configurar_reporte(telefono, tipo_reporte, activar):
    try:
        campo = f"reporte_{tipo_reporte}"
        sb.table("usuarios").update({campo: activar}).eq("telefono", telefono).execute()
        estado = "activado" if activar else "desactivado"
        return f"Reporte {tipo_reporte} {estado}.\n\nEscribe 'Mis reportes' para ver tu configuracion."
    except Exception as e:
        print("Error configurando reporte:", e)
        return "Error actualizando configuracion."

@app.post("/webhook")
async def webhook(Body: str = Form(...), From: str = Form(...)):
    print(f"Mensaje de whatsapp:{From}: {Body}")
    registrar_usuario(From)
    datos = analizar(Body)
    print("Analisis:", datos)

    if not datos.get("es_financiero"):
        es_saludo = any(s in Body.lower() for s in [
            "hola", "hi", "hey", "buenas", "buen dia", "buenas tardes",
            "buenas noches", "saludos", "que tal", "como estas", "hello"
        ])
        if es_saludo:
            return xml(
                "Hola! Soy Aibi, tu asistente financiero personal.\n\n"
                "Estoy aqui para ayudarte a controlar tu dinero de forma simple.\n\n"
                "Puedes decirme:\n"
                "Gaste 15 soles en almuerzo\n"
                "Ingrese 500 de sueldo\n"
                "Cuanto tengo?\n"
                "Mi mayor gasto\n"
                "Cuanto gaste en comida?\n"
                "Meta: Viaje a Cusco S/500\n"
                "Mis metas\n"
                "Activa reporte diario\n\n"
                "En que te puedo ayudar hoy?" +
                tip()
            )
        return xml(
            "No entendi tu mensaje.\n\n"
            "Puedes decirme:\n"
            "Gaste 15 soles en almuerzo\n"
            "Cuanto tengo?\n"
            "Mis metas\n\n"
            "O escribe Hola para ver todas mis funciones." +
            tip()
        )

    accion = datos.get("accion")

    if accion == "registrar":
        guardado = guardar(From, datos)
        tipo = datos.get("tipo", "gasto")
        monto = datos.get("monto", 0)
        cat = datos.get("categoria", "Otro")
        desc = datos.get("descripcion", Body)
        emoji = "Gasto" if tipo == "gasto" else "Ingreso"
        msg = f"{emoji} registrado!\n\n{desc}\nS/ {monto}\n{cat}"
        if random.random() > 0.6:
            msg += tip()
        return xml(msg)

    if accion == "consultar":
        return xml(resumen(From))

    if accion == "editar":
        return xml(editar(From, datos.get("descripcion_buscar", ""), datos.get("monto_nuevo", 0)))

    if accion == "eliminar":
        return xml(eliminar(From, datos.get("descripcion_buscar", "")))

    if accion == "consulta_avanzada":
        return xml(consulta_avanzada(From, datos.get("filtro", ""), datos.get("categoria")))

    if accion == "metas":
        return xml(ver_metas(From))

    if accion == "crear_meta":
        return xml(crear_meta(From, datos.get("nombre", "Meta"), datos.get("monto_objetivo", 0)))

    if accion == "configurar_reporte":
        return xml(configurar_reporte(From, datos.get("tipo_reporte", ""), datos.get("activar", True)))

    return xml(
        "No entendi tu mensaje.\n\n"
        "Escribe Hola para ver todo lo que puedo hacer." +
        tip()
    )

@app.get("/")
def inicio():
    return {
        "aibi": "v2 corriendo",
        "funciones": ["registrar", "consultar", "editar", "eliminar", "metas", "reportes"]
    }
