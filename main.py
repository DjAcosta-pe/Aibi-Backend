from fastapi import FastAPI, Request
from groq import Groq
from supabase import create_client
from datetime import datetime, timezone
import json, os, random, httpx

app = FastAPI()

# Inicialización de clientes (IA y Base de Datos)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
sb = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Lista original de tips
TIPS = [
    "Ahorrar el 10% de cada ingreso es el primer paso hacia la libertad financiera.",
    "Regla 50/30/20: 50% necesidades, 30% deseos, 20% ahorro.",
    "Un fondo de emergencia de 3 meses de gastos te protege de cualquier imprevisto.",
    "Los pequeños gastos diarios pueden sumar más de S/300 al mes sin que te des cuenta.",
    "El mejor momento para ahorrar fue ayer. El segundo mejor momento es hoy.",
    "Pagar tus deudas primero es la mejor inversión que puedes hacer.",
    "Registrar tus gastos diariamente tarda menos de 30 segundos y puede cambiar tu vida.",
]

def tip():
    return f"\n\nTip Aibi: {random.choice(TIPS)}"

async def enviar_mensaje(chat_id, texto):
    """Envía un mensaje de texto al usuario por Telegram"""
    async with httpx.AsyncClient() as c:
        await c.post(f"{TELEGRAM_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": texto
        })

# ==========================================
# GESTIÓN DE USUARIO Y ESTADOS
# ==========================================

def obtener_usuario(telefono):
    """Obtiene el usuario o lo crea si no existe (incluyendo su estado_bot)"""
    try:
        res = sb.table("usuarios").select("*").eq("telefono", telefono).execute()
        if res.data:
            return res.data[0]
        
        # Si no existe, lo registramos (equivalente a tu antiguo registrar_usuario)
        nuevo = sb.table("usuarios").insert({
            "telefono": telefono,
            "reporte_diario": False,
            "reporte_semanal": True,
            "reporte_mensual": True,
            "activo": True,
            "estado_bot": "normal"
        }).execute()
        return nuevo.data[0]
    except Exception as e:
        print("Error obteniendo usuario:", e)
        return None

def actualizar_estado_usuario(telefono, nuevo_estado):
    """Actualiza la memoria a corto plazo del bot para este usuario"""
    try:
        sb.table("usuarios").update({"estado_bot": nuevo_estado}).eq("telefono", telefono).execute()
        return True
    except Exception as e:
        print("Error actualizando estado:", e)
        return False

# ==========================================
# CEREBRO IA (GROQ)
# ==========================================

def analizar(texto):
    """Analiza la intención del usuario devolviendo un JSON estructurado"""
    try:
        hoy = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": f"""Eres Aibi, un asesor financiero personal de élite. Hoy es {hoy}.
Analiza el mensaje y responde SOLO JSON sin texto extra.

Acciones posibles:
- Registrar gasto/ingreso: {{"accion":"registrar","tipo":"gasto"|"ingreso","monto":numero,"categoria":"Comida"|"Transporte"|"Salud"|"Entretenimiento"|"Trabajo"|"Ahorro"|"Otro","descripcion":"texto","es_financiero":true}}
- Saldo/Balance/Resumen: {{"accion":"consultar","es_financiero":true}}
- Editar gasto: {{"accion":"editar","descripcion_buscar":"texto a buscar","monto_nuevo":numero,"es_financiero":true}}
- Eliminar gasto: {{"accion":"eliminar","descripcion_buscar":"texto a buscar","es_financiero":true}}
- Consultas avanzadas: {{"accion":"consulta_avanzada","filtro":"categoria"|"mayor_gasto","categoria":"nombre si aplica","es_financiero":true}}
- Ver metas: {{"accion":"metas","es_financiero":true}}
- Crear meta: {{"accion":"crear_meta","nombre":"nombre","monto_objetivo":numero,"fecha_limite":"YYYY-MM-DD"|null,"mensaje_asesor":"Redacta como experto: indica ahorro mensual y donde recortar","es_financiero":true}}
- Abonar meta: {{"accion":"abonar_meta","nombre_buscar":"palabra clave","monto":numero,"es_financiero":true}}
- REINICIAR DATOS (borrar todo, cuenta, historial): {{"accion":"solicitar_reinicio","es_financiero":true}}
- Configurar reportes: {{"accion":"configurar_reporte","tipo_reporte":"diario"|"semanal"|"mensual","activar":true|false,"es_financiero":true}}
- No es financiero: {{"accion":"ninguna","es_financiero":false}}"""},
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

# ==========================================
# LÓGICA DE NEGOCIO Y BASE DE DATOS
# ==========================================

async def procesar_reinicio(telefono, chat_id, texto):
    """Maneja la confirmación de reinicio de cuenta (Soft Delete total)"""
    t = texto.lower().strip()
    palabras_afirmativas = ["si", "sí", "confirm", "acepto", "borra", "dale", "ok", "claro", "yes"]
    palabras_negativas = ["no", "cancelar", "detener", "nunca"]
    
    if any(p in t for p in palabras_afirmativas):
        try:
            # Borrado Lógico (Soft Delete)
            sb.table("transacciones").update({"eliminado": True}).eq("telefono", telefono).execute()
            sb.table("metas").update({"eliminado": True}).eq("telefono", telefono).execute()
            actualizar_estado_usuario(telefono, "normal")
            await enviar_mensaje(chat_id, "✅ Hecho. He reiniciado tu historial y metas.\n\nPara mí, eres una hoja en blanco lista para el éxito financiero. 🚀 Empieza diciéndome qué gastaste o ingresaste hoy.")
        except Exception as e:
            actualizar_estado_usuario(telefono, "normal")
            await enviar_mensaje(chat_id, "❌ Hubo un error de base de datos al intentar borrar. Intenta de nuevo más tarde.")
            
    elif any(p in t for p in palabras_negativas):
        actualizar_estado_usuario(telefono, "normal")
        await enviar_mensaje(chat_id, "Entendido. No he borrado nada. Seguimos con el plan. 💼")
    else:
        await enviar_mensaje(chat_id, "Por favor, sé más directo. Responde 'SÍ' para confirmar el reinicio o 'NO' para cancelar.")

def guardar(telefono, datos):
    try:
        sb.table("transacciones").insert({
            "telefono": telefono, 
            "tipo": datos.get("tipo"), 
            "monto": datos.get("monto"),
            "categoria": datos.get("categoria"), 
            "descripcion": datos.get("descripcion"),
            "fecha": datetime.now(timezone.utc).isoformat(), 
            "eliminado": False
        }).execute()
        return True
    except Exception as e: 
        print("Error al guardar:", e)
        return False

def editar(telefono, desc_buscar, monto_nuevo):
    try:
        res = sb.table("transacciones").select("*").eq("telefono", telefono).eq("eliminado", False).ilike("descripcion", f"%{desc_buscar}%").order("id", desc=True).limit(1).execute()
        if not res.data: 
            return f"No encontré un gasto reciente con '{desc_buscar}'."
        reg = res.data[0]
        sb.table("transacciones").update({"monto": monto_nuevo}).eq("id", reg["id"]).execute()
        return f"¡Listo! Actualicé '{reg['descripcion']}' de S/ {reg['monto']} a S/ {monto_nuevo}"
    except Exception as e: 
        return "Error al editar."

def eliminar(telefono, desc_buscar):
    try:
        res = sb.table("transacciones").select("*").eq("telefono", telefono).eq("eliminado", False).ilike("descripcion", f"%{desc_buscar}%").order("id", desc=True).limit(1).execute()
        if not res.data: 
            return f"No encontré un gasto con '{desc_buscar}'."
        reg = res.data[0]
        # Soft delete individual
        sb.table("transacciones").update({"eliminado": True}).eq("id", reg["id"]).execute()
        return f"Eliminé '{reg['descripcion']}' de S/ {reg['monto']} en {reg['categoria']}."
    except Exception as e: 
        return "Error al eliminar."

def resumen(telefono):
    try:
        data = sb.table("transacciones").select("*").eq("telefono", telefono).eq("eliminado", False).execute().data
        if not data: 
            return "No tienes registros activos aún.\n\nEmpieza diciéndome:\nGasté 10 soles en menú"
        
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
        else: consejo = f"¡Excelente! Solo gastas el {pct}% de tus ingresos."
        
        signo = "+" if bal >= 0 else ""
        return f"Tu resumen Aibi:\n\nIngresos: S/ {ing:.0f}\nGastos:   S/ {gas:.0f}\nBalance:  {signo}S/ {bal:.0f}\n\nTop gastos:\n{top_txt}\n\n{consejo}{tip()}"
    except Exception as e: 
        return "Error consultando datos."

def consulta_avanzada(telefono, filtro, categoria=None):
    try:
        query = sb.table("transacciones").select("*").eq("telefono", telefono).eq("tipo", "gasto").eq("eliminado", False)
        if categoria: 
            query = query.eq("categoria", categoria)
            
        data = query.execute().data
        if not data: 
            return "No encontré gastos con ese criterio."
            
        if filtro == "mayor_gasto":
            mayor = max(data, key=lambda x: x["monto"])
            return f"Tu mayor gasto es:\n\n{mayor['descripcion']}\nS/ {mayor['monto']}\n{mayor['categoria']}"
            
        if filtro == "categoria" and categoria:
            total = sum(r["monto"] for r in data)
            return f"Total en {categoria}:\n\nS/ {total:.0f}\n{len(data)} transacciones{tip()}"
            
        total = sum(r["monto"] for r in data)
        return f"Total encontrado: S/ {total:.0f} en {len(data)} transacciones."
    except Exception as e: 
        return "Error en la consulta."

def ver_metas(telefono):
    try:
        data = sb.table("metas").select("*").eq("telefono", telefono).eq("completada", False).eq("eliminado", False).execute().data
        if not data: 
            return "No tienes metas activas.\n\nCrea una así:\nQuiero ahorrar 500 para un viaje en diciembre"
            
        resp = "🎯 Tus metas de ahorro:\n"
        for m in data:
            pct = round((m["monto_actual"] / m["monto_objetivo"]) * 100) if m["monto_objetivo"] > 0 else 0
            faltan = m["monto_objetivo"] - m["monto_actual"]
            barra = ("=" * (pct // 10)) + ("-" * (10 - pct // 10))
            fecha_txt = f"\n📅 Límite: {m['fecha_limite']}" if m.get('fecha_limite') else ""
            resp += f"\n{m['nombre']}{fecha_txt}\n[{barra}] {pct}%\nS/ {m['monto_actual']:.0f} de S/ {m['monto_objetivo']:.0f}\nFaltan: S/ {faltan:.0f}\n"
        return resp + tip()
    except Exception as e: 
        return "Error consultando metas."

def crear_meta(telefono, nombre, monto_obj, fecha_limite=None, mensaje_asesor=None):
    try:
        sb.table("metas").insert({
            "telefono": telefono, 
            "nombre": nombre, 
            "monto_objetivo": monto_obj,
            "monto_actual": 0, 
            "completada": False, 
            "fecha_limite": fecha_limite, 
            "eliminado": False
        }).execute()
        
        return f"🎯 ¡Meta Registrada!\n\n{mensaje_asesor}" if mensaje_asesor else f"Meta creada!\n\n{nombre}\nObjetivo: S/ {monto_obj:.0f}"
    except Exception as e: 
        return "Error creando la meta."

def abonar_meta(telefono, nombre_buscar, monto):
    try:
        res = sb.table("metas").select("*").eq("telefono", telefono).eq("completada", False).eq("eliminado", False).ilike("nombre", f"%{nombre_buscar}%").execute()
        if not res.data: 
            return f"No encontré la meta '{nombre_buscar}'."
            
        meta = res.data[0]
        nuevo = meta["monto_actual"] + monto
        completada = nuevo >= meta["monto_objetivo"]
        
        sb.table("metas").update({"monto_actual": nuevo, "completada": completada}).eq("id", meta["id"]).execute()
        
        if completada: 
            return f"🎉 ¡Felicidades! Has completado tu meta '{meta['nombre']}' (S/ {nuevo:.0f}).\n\n¡Eres un maestro de la disciplina financiera! ¿Cuál será tu próximo objetivo?"
            
        pct = round((nuevo / meta["monto_objetivo"]) * 100)
        faltan = meta["monto_objetivo"] - nuevo
        return f"🔥 ¡Excelente abono!\n\nAgregaste S/ {monto:.0f} a '{meta['nombre']}'.\nProgreso: {pct}% (S/ {nuevo:.0f} de S/ {meta['monto_objetivo']:.0f}).\nSolo faltan S/ {faltan:.0f}. ¡Sigue así!"
    except Exception as e: 
        return "Error al abonar."

def configurar_reporte(telefono, tipo_reporte, activar):
    try:
        sb.table("usuarios").update({f"reporte_{tipo_reporte}": activar}).eq("telefono", telefono).execute()
        return f"Reporte {tipo_reporte} {'activado' if activar else 'desactivado'}."
    except Exception as e: 
        return "Error actualizando configuración."

# ==========================================
# ENDPOINT PRINCIPAL (WEBHOOK)
# ==========================================

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "message" not in data: 
        return {"ok": True}
        
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    texto = msg.get("text", "")
    telefono = str(chat_id)
    
    print(f"Mensaje de Telegram {chat_id}: {texto}")
    
    # 1. Obtener usuario de la base de datos
    usuario = obtener_usuario(telefono)
    
    # 2. Atajar el mensaje si estamos esperando confirmación de reinicio
    if usuario and usuario.get("estado_bot") == "esperando_reinicio":
        await procesar_reinicio(telefono, chat_id, texto)
        return {"ok": True}

    # 3. Flujo normal: Analizar con IA
    datos = analizar(texto)
    accion = datos.get("accion")
    
    print("Análisis IA:", datos)

    # 4. Procesar Saludos y Entradas no financieras
    if not datos.get("es_financiero"):
        es_saludo = any(s in texto.lower() for s in ["hola", "hi", "hey", "buenas", "buen dia", "buenas tardes", "buenas noches", "saludos", "que tal", "como estas", "hello", "start"])
        if es_saludo:
            await enviar_mensaje(chat_id,
                "¡Hola! Soy Aibi, tu asesor financiero personal de élite. 🎩\n\n"
                "Estoy aquí para ayudarte a controlar tu dinero y lograr tus objetivos.\n\n"
                "Puedes decirme:\n"
                "📉 *Gasté 15 soles en almuerzo*\n"
                "📈 *Ingresé 500 de sueldo*\n"
                "📊 *¿Cuánto tengo?*\n"
                "🔍 *Mi mayor gasto*\n"
                "🎯 *Quiero ahorrar 1500 para un viaje en diciembre*\n"
                "💰 *Aboné 50 a mi viaje*\n"
                "🏆 *Mis metas*\n\n"
                "¿En qué te puedo ayudar hoy?" + tip()
            )
        else:
            await enviar_mensaje(chat_id,
                "No entendí tu mensaje.\n\n"
                "Puedes decirme:\n"
                "Gasté 15 soles en almuerzo\n"
                "¿Cuánto tengo?\n"
                "Mis metas\n\n"
                "O escribe Hola para ver todas mis funciones." + tip()
            )
        return {"ok": True}

    # 5. Ejecutar la acción financiera detectada
    if accion == "solicitar_reinicio":
        exito = actualizar_estado_usuario(telefono, "esperando_reinicio")
        if exito:
            await enviar_mensaje(chat_id, "⚠️ *ATENCIÓN*: Estás a punto de reiniciar todo tu historial financiero y metas.\n\nEsta acción no se puede deshacer. ¿Estás seguro? Responde *SÍ* para confirmar o *NO* para cancelar.")
        else:
            await enviar_mensaje(chat_id, "⚠️ Error de sistema. Por favor revisa en Supabase si tu tabla 'usuarios' tiene la columna 'estado_bot'.")
            
    elif accion == "registrar":
        guardar(telefono, datos)
        emoji = "📉 Gasto" if datos.get("tipo") == "gasto" else "📈 Ingreso"
        msg_resp = f"✅ {emoji} registrado!\n\n{datos.get('descripcion')}\nS/ {datos.get('monto')}\n{datos.get('categoria')}"
        if random.random() > 0.6: 
            msg_resp += tip()
        await enviar_mensaje(chat_id, msg_resp)
        
    elif accion == "consultar": 
        await enviar_mensaje(chat_id, resumen(telefono))
        
    elif accion == "editar": 
        await enviar_mensaje(chat_id, editar(telefono, datos.get("descripcion_buscar", ""), datos.get("monto_nuevo", 0)))
        
    elif accion == "eliminar": 
        await enviar_mensaje(chat_id, eliminar(telefono, datos.get("descripcion_buscar", "")))
        
    elif accion == "consulta_avanzada": 
        await enviar_mensaje(chat_id, consulta_avanzada(telefono, datos.get("filtro", ""), datos.get("categoria")))
        
    elif accion == "metas": 
        await enviar_mensaje(chat_id, ver_metas(telefono))
        
    elif accion == "crear_meta": 
        await enviar_mensaje(chat_id, crear_meta(telefono, datos.get("nombre"), datos.get("monto_objetivo"), datos.get("fecha_limite"), datos.get("mensaje_asesor")))
        
    elif accion == "abonar_meta": 
        await enviar_mensaje(chat_id, abonar_meta(telefono, datos.get("nombre_buscar"), datos.get("monto", 0)))
        
    elif accion == "configurar_reporte": 
        await enviar_mensaje(chat_id, configurar_reporte(telefono, datos.get("tipo_reporte", ""), datos.get("activar", True)))

    return {"ok": True}

@app.get("/")
def inicio():
    return {"aibi": "v2.4 - Completo, Metas Inteligentes y Soft Delete activo"}
