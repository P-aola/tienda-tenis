import os
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, abort, jsonify, session, flash
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError
from bson import ObjectId

app = Flask(__name__)
# Se requiere una secret_key para el manejo de sesiones del visitante (reserva_id)
app.secret_key = os.getenv("SECRET_KEY", "secreto-sneakerzone-temporal")

# Configuración de MongoDB Atlas
MONGO_URI = "mongodb+srv://cruzmadrigalpaolacbtis272_db_user:facil123@buffalo01.axmhp0e.mongodb.net/"
cliente = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000,
    tz_aware=True
)
base_datos = cliente["tienda_tenis"]
alumnos = base_datos["productos"]
reservas = base_datos["reservas"]

DURACION_RESERVA_MINUTOS = 5

# Crear índices para optimizar y asegurar las reservas únicas por usuario
try:
    reservas.create_index([("reserva_id", 1), ("producto_id", 1)], unique=True)
    reservas.create_index("vence_en")
except Exception:
    pass

def ahora_utc():
    return datetime.now(timezone.utc)

def obtener_reserva_id():
    if not session.get("reserva_id"):
        session["reserva_id"] = uuid.uuid4().hex
    return session["reserva_id"]

def liberar_reservas_vencidas():
    vencidas = list(reservas.find({
        "estado": "activa",
        "vence_en": {"$lte": ahora_utc()}
    }))
    for candidata in vencidas:
        with cliente.start_session() as mongo_session:
            with mongo_session.start_transaction():
                eliminada = reservas.find_one_and_delete(
                    {"_id": candidata["_id"], "estado": "activa"},
                    session=mongo_session
                )
                if eliminada:
                    alumnos.update_one(
                        {"_id": eliminada["producto_id"]},
                        {"$inc": {"reservadas": -eliminada["cantidad"]}},
                        session=mongo_session
                    )

def reservar_unidad(producto_id, reserva_id):
    ahora = ahora_utc()
    vence = ahora + timedelta(minutes=DURACION_RESERVA_MINUTOS)
    oid = ObjectId(producto_id)
    with cliente.start_session() as mongo_session:
        with mongo_session.start_transaction():
            producto = alumnos.find_one_and_update(
                {
                    "_id": oid,
                    "$expr": {
                        "$gt": [
                            {
                                "$subtract": [
                                    {"$ifNull": ["$existencias", 0]},
                                    {"$ifNull": ["$reservadas", 0]}
                                ]
                            },
                            0
                        ]
                    }
                },
                {"$inc": {"reservadas": 1}},
                return_document=ReturnDocument.AFTER,
                session=mongo_session
            )
            if producto is None:
                return False
            reservas.update_one(
                {"reserva_id": reserva_id, "producto_id": oid},
                {
                    "$inc": {"cantidad": 1},
                    "$set": {"estado": "activa", "vence_en": vence},
                    "$setOnInsert": {"creada_en": ahora}
                },
                upsert=True,
                session=mongo_session
            )
            return True

def leer_formulario(datos=None):
    if datos is None:
        datos = request.form
    campos = ("nombre", "categoria", "estado")
    if any(not isinstance(datos.get(c, ""), str) for c in campos):
        abort(400, description="Los campos deben contener texto.")
    nombre = datos.get("nombre", "").strip()
    categoria = datos.get("categoria", "").strip()
    estado = datos.get("estado", "").strip()
    if not nombre or not categoria or not estado:
        abort(400, description="Completa nombre, categoría y estado.")
    if len(nombre) > 80 or len(categoria) > 20:
        abort(400, description="Máximo: nombre 80 y categoría 20.")
    if estado not in ["Disponible", "Agotado"]:
        abort(400, description="Selecciona un estado válido.")
    
    try:
        existencias = int(datos.get("existencias", 10))
    except ValueError:
        existencias = 10

    return {
        "nombre": nombre, 
        "categoria": categoria, 
        "estado": estado,
        "existencias": existencias,
        "reservadas": 0
    }

def buscar_alumno(id):
    if not ObjectId.is_valid(id):
        abort(404, description="La clave del producto no es válida.")
    alumno = alumnos.find_one({"_id": ObjectId(id)})
    if alumno is None:
        abort(404, description="Este producto ya no existe.")
    return alumno

@app.route("/")
def index():
    try:
        liberar_reservas_vencidas()
        productos = list(alumnos.find())
        for p in productos:
            p["disponibles"] = max(0, int(p.get("existencias", 0)) - int(p.get("reservadas", 0)))
        return render_template("index.html", productos=productos)
    except Exception as e:
        return f"<h3>¡Aquí está la causa del error!</h3><p style='color:red;'>{str(e)}</p>"

@app.route("/agregar", methods=["POST"])
def agregar():
    datos = leer_formulario()
    alumnos.insert_one(datos)
    return redirect(url_for("index"))

@app.route("/editar/<id>", methods=["GET", "POST"])
def editar(id):
    alumno = buscar_alumno(id)
    if request.method == "POST":
        datos = leer_formulario()
        datos["existencias"] = alumno.get("existencias", 10)
        datos["reservadas"] = alumno.get("reservadas", 0)
        alumnos.update_one({"_id": alumno["_id"]}, {"$set": datos})
        return redirect(url_for("index"))
    return render_template("editar.html", alumno=alumno)

@app.route("/eliminar/<id>", methods=["POST"])
def eliminar(id):
    alumno = buscar_alumno(id)
    alumnos.delete_one({"_id": alumno["_id"]})
    return redirect(url_for("index"))

@app.route("/reservar/<id>", methods=["POST"])
def reservar(id):
    liberar_reservas_vencidas()
    reserva_id = obtener_reserva_id()
    if reservar_unidad(id, reserva_id):
        return jsonify({"success": True, "message": "Producto reservado temporalmente por 5 minutos."}), 200
    else:
        return jsonify({"success": False, "message": "La última unidad acaba de ser reservada por otro usuario."}), 409

@app.route("/ayuda")
def ayuda():
    fecha = datetime.now().strftime("%d/%m/%Y")
    return render_template("ayuda.html", fecha=fecha)

@app.errorhandler(PyMongoError)
def error_mongo(error):
    mensaje = "No fue posible conectar con la base de datos."
    if request.path.startswith("/api/"):
        return jsonify({"error": mensaje}), 503
    return render_template("error.html", mensaje=mensaje), 503

def producto_json(producto):
    return {
        "id": str(producto["_id"]),
        "nombre": producto["nombre"],
        "categoria": producto["categoria"],
        "estado": producto["estado"],
        "existencias": producto.get("existencias", 0),
        "reservadas": producto.get("reservadas", 0),
        "disponibles": max(0, int(producto.get("existencias", 0)) - int(producto.get("reservadas", 0)))
    }

def leer_json():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        abort(400, description="Envía un objeto JSON válido.")
    return leer_formulario(datos)

@app.route("/api/productos", methods=["GET", "POST"])
def api_productos():
    liberar_reservas_vencidas()
    if request.method == "POST":
        datos = leer_json()
        resultado = alumnos.insert_one(datos)
        producto = buscar_alumno(str(resultado.inserted_id))
        return jsonify(producto_json(producto)), 201
    lista = alumnos.find().sort("nombre", 1)
    return jsonify([producto_json(p) for p in lista])

@app.route("/api/productos/<id>", methods=["GET", "PUT", "DELETE"])
def api_producto(id):
    producto = buscar_alumno(id)
    if request.method == "PUT":
        datos = leer_json()
        alumnos.update_one({"_id": producto["_id"]}, {"$set": datos})
        return jsonify(producto_json(buscar_alumno(id)))
    if request.method == "DELETE":
        alumnos.delete_one({"_id": producto["_id"]})
        return "", 204
    return jsonify(producto_json(producto))

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
def error_peticion(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return render_template(
        "error.html", mensaje=error.description
    ), error.code

@app.route("/carrito")
def ver_carrito():
    liberar_reservas_vencidas()
    reserva_id = session.get("reserva_id")
    productos_carrito = []
    
    items = list(reservas.find({
        "reserva_id": reserva_id,
        "estado": "activa",
        "vence_en": {"$gt": ahora_utc()}
    })) if reserva_id else []

    for item in items:
        producto = alumnos.find_one({"_id": item["producto_id"]})
        if not producto:
            continue
        productos_carrito.append({
            "id": str(producto["_id"]),
            "nombre": producto.get("nombre", "Tenis"),
            "cantidad": int(item["cantidad"])
        })

    vence_en = min((i["vence_en"] for i in items), default=None)
    return render_template("carrito.html", productos=productos_carrito, vence_en=vence_en)

@app.route("/carrito/eliminar/<producto_id>", methods=["POST"])
def carrito_eliminar(producto_id):
    if not ObjectId.is_valid(producto_id):
        abort(404)
    reserva_id = session.get("reserva_id")
    oid = ObjectId(producto_id)
    
    with cliente.start_session() as mongo_session:
        with mongo_session.start_transaction():
            eliminada = reservas.find_one_and_delete(
                {
                    "reserva_id": reserva_id,
                    "producto_id": oid,
                    "estado": "activa"
                },
                session=mongo_session
            )
            if eliminada:
                alumnos.update_one(
                    {"_id": oid},
                    {"$inc": {"reservadas": -eliminada["cantidad"]}},
                    session=mongo_session
                )
                
    flash("Reserva cancelada y producto liberado con éxito.", "success")
    return redirect(url_for("ver_carrito"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)