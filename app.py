import os
import uuid
from urllib.parse import urlparse, quote
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

from flask import (
    Flask, render_template, request, redirect,
    url_for, abort, jsonify, session, flash
)

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import PyMongoError
from bson import ObjectId


# =====================================================
# CONFIGURACIÓN DE FLASK
# =====================================================

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "Falta configurar la variable SECRET_KEY en el archivo .env."
    )


# =====================================================
# CONEXIÓN CON MONGODB ATLAS
# =====================================================

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError(
        "Falta configurar la variable de entorno MONGO_URI."
    )

cliente = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000,
    tz_aware=True
)

base_datos = cliente["tienda_tenis"]

productos = base_datos["productos"]
reservas = base_datos["reservas"]

DURACION_RESERVA_MINUTOS = 5


# =====================================================
# ÍNDICES DE MONGODB
# =====================================================

try:
    reservas.create_index(
        [("reserva_id", 1), ("producto_id", 1)],
        unique=True
    )

    reservas.create_index("vence_en")

except PyMongoError:
    app.logger.exception("No se pudieron crear los índices.")


# =====================================================
# FUNCIONES GENERALES
# =====================================================

def ahora_utc():
    return datetime.now(timezone.utc)


def obtener_reserva_id():
    if not session.get("reserva_id"):
        session["reserva_id"] = uuid.uuid4().hex

    return session["reserva_id"]


def validar_url_imagen(url):

    url = url.strip()

    if not url:
        return ""

    if len(url) > 1000:
        abort(400, description="La URL de la imagen es demasiado larga.")

    try:
        partes = urlparse(url)

        if partes.scheme not in ("http", "https") or not partes.netloc:
            abort(
                400,
                description="La imagen debe tener una URL válida que comience con http:// o https://."
            )

    except ValueError:
        abort(400, description="La URL de la imagen no es válida.")

    return url


def liberar_reservas_vencidas():

    vencidas = list(reservas.find({
        "estado": "activa",
        "vence_en": {"$lte": ahora_utc()}
    }))

    for candidata in vencidas:

        with cliente.start_session() as mongo_session:

            with mongo_session.start_transaction():

                eliminada = reservas.find_one_and_delete(
                    {
                        "_id": candidata["_id"],
                        "estado": "activa",
                        "vence_en": {"$lte": ahora_utc()}
                    },
                    session=mongo_session
                )

                if eliminada:

                    productos.update_one(
                        {"_id": eliminada["producto_id"]},
                        {
                            "$inc": {
                                "reservadas": -eliminada["cantidad"]
                            }
                        },
                        session=mongo_session
                    )


def reservar_unidad(producto_id, reserva_id):

    ahora = ahora_utc()

    vence = ahora + timedelta(
        minutes=DURACION_RESERVA_MINUTOS
    )

    oid = ObjectId(producto_id)

    with cliente.start_session() as mongo_session:

        with mongo_session.start_transaction():

            producto = productos.find_one_and_update(
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
                {
                    "$inc": {"reservadas": 1}
                },
                return_document=ReturnDocument.AFTER,
                session=mongo_session
            )

            if producto is None:
                return False

            reservas.update_one(
                {
                    "reserva_id": reserva_id,
                    "producto_id": oid
                },
                {
                    "$inc": {"cantidad": 1},
                    "$set": {
                        "estado": "activa",
                        "vence_en": vence
                    },
                    "$setOnInsert": {
                        "creada_en": ahora
                    }
                },
                upsert=True,
                session=mongo_session
            )

            return True


# =====================================================
# LECTURA Y VALIDACIÓN DE FORMULARIOS
# =====================================================

def leer_formulario(datos=None):

    if datos is None:
        datos = request.form

    campos = ("nombre", "categoria", "estado")

    if any(
        not isinstance(datos.get(c, ""), str)
        for c in campos
    ):
        abort(400, description="Los campos deben contener texto.")

    nombre = datos.get("nombre", "").strip()
    categoria = datos.get("categoria", "").strip()
    estado = datos.get("estado", "").strip()

    if not nombre or not categoria or not estado:
        abort(
            400,
            description="Completa nombre, categoría y estado."
        )

    if len(nombre) > 80 or len(categoria) > 20:
        abort(
            400,
            description="Máximo: nombre 80 y categoría 20."
        )

    if estado not in ["Disponible", "Agotado"]:
        abort(400, description="Selecciona un estado válido.")

    try:
        existencias = int(datos.get("existencias", 10))
    except (ValueError, TypeError):
        abort(400, description="Las existencias deben ser un número.")

    if existencias < 0:
        abort(400, description="Las existencias no pueden ser negativas.")

    imagen = datos.get("imagen", "")

    if not isinstance(imagen, str):
        abort(400, description="La imagen debe ser una URL de texto.")

    imagen = validar_url_imagen(imagen)

    return {
        "nombre": nombre,
        "categoria": categoria,
        "estado": estado,
        "existencias": existencias,
        "imagen": imagen,
        "reservadas": 0
    }


def buscar_producto_tienda(id):

    if not ObjectId.is_valid(id):
        abort(404, description="La clave del producto no es válida.")

    prod = productos.find_one({
        "_id": ObjectId(id)
    })

    if prod is None:
        abort(404, description="Este producto ya no existe.")

    return prod


# =====================================================
# CATÁLOGO PRINCIPAL (CON GENERACIÓN DE QR CODIFICADO)
# =====================================================

@app.route("/")
def index():

    liberar_reservas_vencidas()

    lista_productos = list(productos.find())

    for p in lista_productos:

        p["disponibles"] = max(
            0,
            int(p.get("existencias", 0)) -
            int(p.get("reservadas", 0))
        )
        
        # Generación de identificador y QR dinámico codificado
        p["id_str"] = str(p["_id"])
        p["enlace_publico"] = url_for('ver_producto', id=p["id_str"], _external=True)
        
        enlace_seguro = quote(p["enlace_publico"], safe="")
        p["enlace_qr"] = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={enlace_seguro}"

    return render_template(
        "index.html",
        productos=lista_productos
    )


# =====================================================
# AGREGAR PRODUCTOS
# =====================================================

@app.route("/agregar", methods=["POST"])
def agregar():

    datos = leer_formulario()

    productos.insert_one(datos)

    flash("Producto agregado correctamente.", "success")

    return redirect(url_for("index"))


# =====================================================
# EDITAR PRODUCTOS
# =====================================================

@app.route("/editar/<id>", methods=["GET", "POST"])
def editar(id):

    prod = buscar_producto_tienda(id)

    if request.method == "POST":

        datos = leer_formulario()

        datos["existencias"] = max(
            prod.get("existencias", 0),
            datos["existencias"]
        )

        datos["reservadas"] = prod.get("reservadas", 0)

        productos.update_one(
            {"_id": prod["_id"]},
            {"$set": datos}
        )

        flash("Producto actualizado correctamente.", "success")

        return redirect(url_for("index"))

    return render_template(
        "editar.html",
        producto=prod
    )


# =====================================================
# ELIMINAR PRODUCTOS
# =====================================================

@app.route("/eliminar/<id>", methods=["POST"])
def eliminar(id):

    prod = buscar_producto_tienda(id)

    if prod.get("reservadas", 0) > 0:
        flash(
            "No puedes eliminar un producto que tiene reservas activas.",
            "error"
        )
        return redirect(url_for("index"))

    productos.delete_one({
        "_id": prod["_id"]
    })

    flash("Producto eliminado correctamente.", "success")

    return redirect(url_for("index"))


# =====================================================
# RESERVAR PRODUCTOS (SOPORTA GET Y POST)
# =====================================================

@app.route("/reservar/<id>", methods=["GET", "POST"])
def reservar(id):

    liberar_reservas_vencidas()

    if not ObjectId.is_valid(id):
        if request.method == "POST":
            return jsonify({"success": False, "message": "Producto no válido."}), 404
        abort(404, description="Producto no válido.")

    reserva_id = obtener_reserva_id()

    if reservar_unidad(id, reserva_id):
        if request.method == "POST":
            return jsonify({
                "success": True,
                "message": "Producto reservado temporalmente por 5 minutos."
            }), 200
        
        flash("Producto reservado temporalmente por 5 minutos.", "success")
        return redirect(url_for("ver_carrito"))

    if request.method == "POST":
        return jsonify({
            "success": False,
            "message": "La última unidad acaba de ser reservada por otro usuario."
        }), 409

    flash("La última unidad acaba de ser reservada por otro usuario.", "error")
    return redirect(url_for("index"))


# =====================================================
# PÁGINA INDIVIDUAL DEL PRODUCTO
# =====================================================

@app.route("/producto/<id>")
def ver_producto(id):

    liberar_reservas_vencidas()

    producto = buscar_producto_tienda(id)

    producto["disponibles"] = max(
        0,
        int(producto.get("existencias", 0)) -
        int(producto.get("reservadas", 0))
    )

    url_producto = (
        request.url_root.rstrip("/") +
        url_for("ver_producto", id=id)
    )

    return render_template(
        "producto.html",
        producto=producto,
        url_producto=url_producto
    )


# =====================================================
# PÁGINA DE AYUDA
# =====================================================

@app.route("/ayuda")
def ayuda():

    fecha = datetime.now().strftime("%d/%m/%Y")

    return render_template(
        "ayuda.html",
        fecha=fecha
    )


# =====================================================
# API: CONVERTIR PRODUCTO A JSON
# =====================================================

def producto_json(producto):

    return {
        "id": str(producto["_id"]),
        "nombre": producto["nombre"],
        "categoria": producto["categoria"],
        "estado": producto["estado"],
        "existencias": producto.get("existencias", 0),
        "reservadas": producto.get("reservadas", 0),
        "disponibles": max(
            0,
            int(producto.get("existencias", 0)) -
            int(producto.get("reservadas", 0))
        ),
        "imagen": producto.get("imagen", "")
    }


def leer_json():

    datos = request.get_json(silent=True)

    if not isinstance(datos, dict):
        abort(400, description="Envía un objeto JSON válido.")

    return leer_formulario(datos)


# =====================================================
# API: LISTAR Y AGREGAR PRODUCTOS
# =====================================================

@app.route("/api/productos", methods=["GET", "POST"])
def api_productos():

    liberar_reservas_vencidas()

    if request.method == "POST":

        datos = leer_json()

        resultado = productos.insert_one(datos)

        producto = buscar_producto_tienda(
            str(resultado.inserted_id)
        )

        return jsonify(producto_json(producto)), 201

    lista = productos.find().sort("nombre", 1)

    return jsonify([
        producto_json(p) for p in lista
    ])


# =====================================================
# API: CONSULTAR, EDITAR Y ELIMINAR UN PRODUCTO
# =====================================================

@app.route("/api/productos/<id>", methods=["GET", "PUT", "DELETE"])
def api_producto(id):

    prod = buscar_producto_tienda(id)

    if request.method == "PUT":

        datos = leer_json()

        datos["existencias"] = max(
            prod.get("existencias", 0),
            datos["existencias"]
        )

        datos["reservadas"] = prod.get("reservadas", 0)

        productos.update_one(
            {"_id": prod["_id"]},
            {"$set": datos}
        )

        return jsonify(
            producto_json(buscar_producto_tienda(id))
        )

    if request.method == "DELETE":

        if prod.get("reservadas", 0) > 0:
            return jsonify({
                "error": "El producto tiene reservas activas."
            }), 409

        productos.delete_one({
            "_id": prod["_id"]
        })

        return "", 204

    return jsonify(producto_json(prod))


# =====================================================
# CARRITO DE RESERVAS
# =====================================================

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

        prod = productos.find_one({
            "_id": item["producto_id"]
        })

        if not prod:
            continue

        productos_carrito.append({
            "id": str(prod["_id"]),
            "nombre": prod.get("nombre", "Tenis"),
            "cantidad": int(item["cantidad"])
        })

    vence_en = min(
        (i["vence_en"] for i in items),
        default=None
    )

    return render_template(
        "carrito.html",
        productos=productos_carrito,
        vence_en=vence_en
    )


# =====================================================
# CANCELAR UNA RESERVA
# =====================================================

@app.route("/carrito/eliminar/<producto_id>", methods=["POST"])
def carrito_eliminar(producto_id):

    if not ObjectId.is_valid(producto_id):
        abort(404)

    reserva_id = session.get("reserva_id")

    if not reserva_id:
        return redirect(url_for("ver_carrito"))

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

                productos.update_one(
                    {"_id": oid},
                    {
                        "$inc": {
                            "reservadas": -eliminada["cantidad"]
                        }
                    },
                    session=mongo_session
                )

    flash(
        "Reserva cancelada y producto liberado con éxito.",
        "success"
    )

    return redirect(url_for("ver_carrito"))


# =====================================================
# MANEJO DE ERRORES
# =====================================================

@app.errorhandler(PyMongoError)
def error_mongo(error):

    app.logger.exception("Error de MongoDB")

    mensaje = "No fue posible conectar con la base de datos."

    if request.path.startswith("/api/"):
        return jsonify({"error": mensaje}), 503

    return render_template(
        "error.html",
        mensaje=mensaje
    ), 503


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
def error_peticion(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "error": error.description
        }), error.code

    return render_template(
        "error.html",
        mensaje=error.description
    ), error.code


# =====================================================
# INICIAR SERVIDOR
# =====================================================

if __name__ == "__main__":

    puerto = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=True,
        use_reloader=False
    )