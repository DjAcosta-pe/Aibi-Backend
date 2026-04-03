from fastapi import FastAPI, Form
from fastapi.responses import Response
from groq import Groq
from supabase import create_client
from datetime import datetime
import json, os, random

app = FastAPI()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

TIPS = [
    "💰 Recuerda: ahorrar el 10% de cada ingreso es el primer paso hacia la libertad financiera.",
    "📊 El 78% de las personas que registran sus gastos diariamente logran sus metas de ahorro.",
    "⚖️ Regla 50/30/20: 50% necesidades, 30% deseos, 20% ahorro. Intenta aplicarla este mes.",
    "🛡️ Un fondo de emergencia de 3 meses de gastos te protege de cualquier imprevisto.",
    "☕ Pequenos gastos diarios sumados pueden representar mas de S/300 al mes sin que te des cuenta.",
]

def xml(msg):
    return Response(content=f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{msg}</Message></Response>', media_type="text/xml")

# -----------------------------------------------
# USUARIOS Y HISTORIAL
# -----------------------------------------------

def obtener_usuario(telefono):
    try:
        result = supabase.table("usuarios").select("*").eq("telefono", telefono).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print("Error obteniendo usuario:", e)
        return None

def actualizar_usuario(telefono, datos):
    try:
        supabase.table("usuarios").update(datos).eq("telefono", telefono).execute()
    except Exception as e:
        print("Error actualizando usuario:", e)

def cargar_historial(usuario):
    try:
        raw = usuario.get("historial") or "[]"
        return json.loads(raw)
    except:
        return []

def guardar_historial(telefono, historial):
    try:
        # Guardar solo los últimos 10 mensajes para no crecer demasiado
        reciente = historial[-10:]
        actualizar_usuario(telefono, {"historial": json.dumps(reciente)})
    except Exception as e:
        print("Error guardando historial:", e)

# -----------------------------------------------
# ONBOARDING
# -----------------------------------------------

def manejar_onboarding(telefono, mensaje, usuario):
    paso = usuario["onboarding_paso"]

    if paso == 1:
        nombre = mensaje.strip().split()[0].capitalize()
        actualizar_usuario(telefono, {"nombre": nombre, "onboarding_paso": 2})
        return xml(f"Mucho gusto, {nombre}! 😊\n\n💵 ¿Cuánto ganas o recibes al mes aproximadamente?\n\nSi tus ingresos son variables escribe:\n\"No tengo fijo\"\n\ny yo te pediré que registres cada vez que te paguen.")

    if paso == 2:
        texto = mensaje.strip().lower()
        if any(p in texto for p in ["no", "variable", "fijo", "vario", "depende"]):
            actualizar_usuario(telefono, {"ingreso_mensual": 0, "onboarding_paso": 3})
            nombre = usuario.get("nombre", "")
            return xml(f"Perfecto {nombre}! 📝 Entonces cada vez que te paguen escríbeme:\n\"Ingrese [monto] de [fuente]\"\n\nEjemplo: Ingrese 500 de trabajo freelance\n\n🎯 Ahora dime... ¿cuál es tu meta financiera más importante?\n\nPor ejemplo:\n- Ahorrar para un viaje\n- Tener un fondo de emergencia\n- Comprar algo específico\n- Salir de deudas")
        else:
            try:
                monto = float(''.join(filter(lambda x: x.isdigit() or x == '.', texto)))
                actualizar_usuario(telefono, {"ingreso_mensual": monto, "onboarding_paso": 3})
                nombre = usuario.get("nombre", "")
                return xml(f"Genial {nombre}! 💪 Anotado.\n\n🎯 ¿Cuál es tu meta financiera más importante ahora mismo?\n\nPor ejemplo:\n- Ahorrar para un viaje\n- Tener un fondo de emergencia\n- Comprar algo específico\n- Salir de deudas")
            except:
                return xml("No entendí bien el monto 😅 ¿Puedes escribir solo el número?\n\nEjemplo: 1500\n\nO si es variable escribe: No tengo fijo")

    if paso == 3:
        actualizar_usuario(telefono, {"metas": mensaje.strip(), "onboarding_paso": 4})
        nombre = usuario.get("nombre", "")
        ingreso = usuario.get("ingreso_mensual", 0)
        consejo = f"Con S/ {ingreso:.0f}/mes, si ahorras el 20% tendrías S/ {ingreso*0.20:.0f} extra cada mes." if ingreso > 0 else "Cada vez que recibas dinero, regístralo conmigo para ir construyendo tu historial."
        return xml(f"Excelente meta, {nombre}! 🌟 Vamos a lograrlo juntos.\n\n{consejo}\n\nYa estás listo para usar Aibi! Puedes decirme:\n📌 Gaste 10 soles en menu\n📌 Ingrese 500 de sueldo\n📌 Cuanto tengo?\n📌 Mis metas\n\n" + random.choice(TIPS))

    return None

# -----------------------------------------------
# IA CON MEMORIA
# -----------------------------------------------

def procesar_mensaje(texto, usuario, historial, balance):
    """
    Función central: analiza el mensaje con contexto completo
    y decide qué hacer. Devuelve (accion, respuesta_texto).
    """
    nombre = usuario.get("nombre", "") if usuario else ""
    ingreso = usuario.get("ingreso_mensual", 0) if usuario else 0
    meta = usuario.get("metas", "") if usuario else ""
    fecha_hoy = datetime.utcnow().strftime("%d de %B del %Y")

    sistema = f"""Eres Aibi, un asistente financiero personal para WhatsApp. Eres amigable, directo y hablas en español.

Datos del usuario:
- Nombre: {nombre or 'desconocido'}
- Ingreso mensual: S/ {ingreso if ingreso else 'variable'}
- Balance actual: S/ {balance:.0f}
- Meta financiera: {meta or 'no definida'}
- Fecha de hoy: {fecha_hoy}

Tu trabajo es entender el mensaje del usuario CONSIDERANDO el historial de la conversación y responder con un JSON:

Si el usuario registra explícitamente un gasto o ingreso (ej: "gasté 10 soles", "me pagaron 500", "ingresé 200 de mi trabajo"):
{{"accion":"registrar","tipo":"gasto" o "ingreso","monto":numero,"categoria":"Comida/Transporte/Salud/Entretenimiento/Trabajo/Ahorro/Otro","descripcion":"descripcion corta","respuesta":"mensaje confirmando el registro"}}

Si el usuario pide ver su resumen, saldo, balance o historial de gastos:
{{"accion":"consultar","respuesta":""}}

Si el usuario quiere ver sus metas:
{{"accion":"metas","respuesta":""}}

Si el usuario quiere borrar su historial o datos:
{{"accion":"borrar","respuesta":""}}

Si el usuario menciona cuánto gana o su ingreso mensual fijo (ej: "gano 550 al mes", "mi sueldo es 1200", "recibo 800 mensuales"):
{{"accion":"actualizar_ingreso","ingreso_mensual":numero,"respuesta":"mensaje confirmando que quedó guardado"}}

Para CUALQUIER OTRA COSA (preguntas, cálculos, consejos, respuestas a preguntas anteriores, conversación):
{{"accion":"conversar","respuesta":"tu respuesta directa aqui, max 6 lineas, personalizada con sus datos"}}

IMPORTANTE: Si el historial muestra que Aibi hizo una pregunta y el usuario está respondiendo esa pregunta, clasifícalo como "conversar" y responde coherentemente. NUNCA registres un número como ingreso/gasto si es una respuesta a una pregunta previa."""

    mensajes = [{"role": "system", "content": sistema}]
    # Agregar historial reciente
    for h in historial[-6:]:
        mensajes.append(h)
    mensajes.append({"role": "user", "content": texto})

    try:
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            temperature=0.3,
            timeout=10
        )
        c = r.choices[0].message.content.strip()
        if not c:
            raise ValueError("Respuesta vacía")
        if "```" in c:
            c = c.split("```")[1].replace("json", "").strip()
        # Si no empieza con { intentar extraer JSON o usar como texto directo
        if not c.startswith("{"):
            return {"accion": "conversar", "respuesta": c}
        return json.loads(c)
    except Exception as e:
        print("Error IA:", e)
        return {"accion": "conversar", "respuesta": "Perdona, tuve un problema. ¿Puedes repetirlo?"}

# -----------------------------------------------
# TRANSACCIONES
# -----------------------------------------------

def guardar(telefono, datos):
    try:
        supabase.table("transacciones").insert({
            "telefono": telefono,
            "tipo": datos.get("tipo"),
            "monto": datos.get("monto"),
            "categoria": datos.get("categoria"),
            "descripcion": datos.get("descripcion"),
            "fecha": datetime.utcnow().isoformat()
        }).execute()
        return True
    except Exception as e:
        print("Error guardando:", e)
        return False

def resumen(telefono, usuario):
    try:
        nombre = usuario.get("nombre", "") if usuario else ""
        data = supabase.table("transacciones").select("*").eq("telefono", telefono).execute().data
        if not data:
            return f"Aún no tienes registros{', ' + nombre if nombre else ''}. Empieza diciéndome: Gasté 10 soles en menú"
        ing = sum(r["monto"] for r in data if r["tipo"] == "ingreso")
        gas = sum(r["monto"] for r in data if r["tipo"] == "gasto")
        bal = ing - gas
        cats = {}
        for r in data:
            if r["tipo"] == "gasto":
                c = r["categoria"] or "Otro"
                cats[c] = cats.get(c, 0) + r["monto"]
        top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
        top_txt = "\n".join([f"  {c}: S/ {m:.0f}" for c, m in top]) if top else "  Sin gastos aún"
        pct = round((gas/ing)*100) if ing > 0 else 0
        if pct > 90: consejo = "⚠️ Alerta: gastas casi todo lo que ganas."
        elif pct > 70: consejo = f"📉 Gastas el {pct}% de tus ingresos. Intenta bajar al 70%."
        else: consejo = f"✅ Excelente! Solo gastas el {pct}% de tus ingresos."
        signo = "+" if bal >= 0 else ""
        encabezado = f"Tu resumen, {nombre}:" if nombre else "Tu resumen:"
        return f"""{encabezado}

💵 Ingresos: S/ {ing:.0f}
💸 Gastos:   S/ {gas:.0f}
📊 Balance:  {signo}S/ {bal:.0f}

🏷️ Top gastos:
{top_txt}

{consejo}

{random.choice(TIPS)}"""
    except Exception as e:
        return "Error al consultar tus datos."

def ver_metas(telefono, usuario):
    try:
        nombre = usuario.get("nombre", "") if usuario else ""
        meta_guardada = usuario.get("metas", "") if usuario else ""
        data = supabase.table("transacciones").select("*").eq("telefono", telefono).execute().data
        ing = sum(r["monto"] for r in data if r["tipo"] == "ingreso")
        gas = sum(r["monto"] for r in data if r["tipo"] == "gasto")
        bal = ing - gas
        ingreso_base = usuario.get("ingreso_mensual", 0) if usuario else 0
        ahorro_rec = ingreso_base * 0.20 if ingreso_base else ing * 0.20
        meta_txt = f"🎯 Tu meta: {meta_guardada}\n\n" if meta_guardada else ""
        return f"""Metas de ahorro{', ' + nombre if nombre else ''}:

{meta_txt}💰 Balance disponible: S/ {bal:.0f}
🐷 Ahorro recomendado (20%): S/ {ahorro_rec:.0f}/mes

Para actualizar tu meta dime:
"Mi nueva meta es: [describe tu objetivo]"

{random.choice(TIPS)}"""
    except:
        return "Aún no tienes metas. Dime: Mi meta es: [tu objetivo]"

def borrar_historial(telefono):
    try:
        supabase.table("transacciones").delete().eq("telefono", telefono).execute()
        actualizar_usuario(telefono, {"historial": "[]"})
        return "🗑️ Listo! Tu historial fue borrado completamente.\n\nPuedes empezar de cero cuando quieras."
    except Exception as e:
        print("Error borrando:", e)
        return "Hubo un error al borrar tus datos. Inténtalo de nuevo."

# -----------------------------------------------
# WEBHOOK
# -----------------------------------------------

@app.post("/webhook")
async def webhook(Body: str = Form(...), From: str = Form(...)):
    print("Mensaje:", Body)

    usuario = obtener_usuario(From)

    # Usuario nuevo
    if not usuario:
        supabase.table("usuarios").insert({"telefono": From, "onboarding_paso": 1, "historial": "[]"}).execute()
        return xml("Hola! Soy Aibi 👋 tu asistente financiero personal.\n\nVoy a ayudarte a controlar tu dinero, alcanzar tus metas y tomar mejores decisiones.\n\n¿Cómo te llamas? 😊")

    # Onboarding
    if usuario["onboarding_paso"] < 4:
        respuesta = manejar_onboarding(From, Body, usuario)
        if respuesta:
            return respuesta

    # Cargar historial y balance
    historial = cargar_historial(usuario)
    try:
        trans = supabase.table("transacciones").select("*").eq("telefono", From).execute().data
        ing = sum(r["monto"] for r in trans if r["tipo"] == "ingreso")
        gas = sum(r["monto"] for r in trans if r["tipo"] == "gasto")
        balance = ing - gas
    except:
        balance = 0

    # Procesar con IA + contexto
    resultado = procesar_mensaje(Body, usuario, historial, balance)
    print("Resultado IA:", resultado)

    accion = resultado.get("accion", "conversar")
    respuesta_ia = resultado.get("respuesta", "")
    nombre = usuario.get("nombre", "")

    # Determinar mensaje final a enviar
    if accion == "registrar":
        guardado = guardar(From, resultado)
        tipo = resultado.get("tipo", "gasto")
        monto = resultado.get("monto", 0)
        cat = resultado.get("categoria", "Otro")
        desc = resultado.get("descripcion", Body)
        emoji = "💸 Gasto" if tipo == "gasto" else "💰 Ingreso"
        tip = random.choice(TIPS) if random.random() > 0.6 else ""
        msg = respuesta_ia if respuesta_ia else f"{emoji} registrado!\n\n📌 {desc}\nS/ {monto}\n🏷️ {cat}\n✅ Guardado!"
        if tip and not respuesta_ia:
            msg += f"\n\n{tip}"
    elif accion == "consultar":
        msg = resumen(From, usuario)
    elif accion == "metas":
        msg = ver_metas(From, usuario)
    elif accion == "borrar":
        msg = borrar_historial(From)
    elif accion == "actualizar_ingreso":
        nuevo_ingreso = resultado.get("ingreso_mensual", 0)
        if nuevo_ingreso:
            actualizar_usuario(From, {"ingreso_mensual": nuevo_ingreso})
        msg = resultado.get("respuesta", f"✅ Listo! Guardé que ganas S/ {nuevo_ingreso} al mes.")
    else:
        # conversar o cualquier otro caso
        if not respuesta_ia:
            msg = f"Hola{', ' + nombre if nombre else ''}! 👋\n\nPuedo ayudarte con:\n📌 Gaste 10 soles en menu\n📌 Ingrese 500 de sueldo\n📌 Cuanto tengo?\n📌 Mis metas\n\n" + random.choice(TIPS)
        else:
            msg = respuesta_ia

    # Guardar el intercambio en el historial (máx 120 chars para respuestas largas)
    resumen_msg = msg if len(msg) < 120 else msg[:120] + "..."
    historial.append({"role": "user", "content": Body})
    historial.append({"role": "assistant", "content": resumen_msg})
    guardar_historial(From, historial)

    return xml(msg)

@app.get("/")
def inicio():
    return {"aibi": "corriendo con memoria de conversacion"}
