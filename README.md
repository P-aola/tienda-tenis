# Demostracion QR con Flask y MongoDB Atlas

Proyecto para mostrar como un codigo QR abre la ficha de un registro guardado en MongoDB Atlas. Esta version esta preparada para ejecutarse en Visual Studio Code, subirse a GitHub y desplegarse en Render.

## Lo unico que debes cambiar

Cada equipo debe colocar su propia cadena de conexion en la variable `MONGO_URI`.

```env
MONGO_URI=mongodb+srv://USUARIO:CONTRASENA@CLUSTER.mongodb.net/?retryWrites=true&w=majority
```

El proyecto ya utiliza:

- Base de datos: `catalogo_qr`
- Coleccion: `productos`
- Comando de Render: `gunicorn app:app`
- Variable del puerto: `PORT`

## 1. Preparar MongoDB Atlas

1. Entra a MongoDB Atlas.
2. Abre tu proyecto y tu cluster.
3. En **Database Access**, crea o revisa un usuario con contrasena.
4. En **Network Access**, agrega las direcciones de salida de Render o el acceso autorizado por el docente.
5. En el cluster, presiona **Connect**.
6. Selecciona **Drivers** o **Connect your application**.
7. Selecciona Python y copia la cadena completa.
8. Sustituye `<password>` por la contrasena real del usuario.

No compartas la cadena de conexion y no la publiques en GitHub.

## 2. Ejecutar en Visual Studio Code

Abre la carpeta del proyecto y abre **Terminal > Nueva terminal**.

### macOS o Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### Windows

```bash
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Abre el archivo `.env` y reemplaza solamente el valor de `MONGO_URI`.

Despues ejecuta:

```bash
python3 app.py
```

En Windows tambien puedes usar:

```bash
python app.py
```

Abre en el navegador:

```text
http://127.0.0.1:5000
```

La primera vez, la aplicacion crea automaticamente cuatro documentos en la coleccion `productos`.

## 3. Demostracion

1. Abre una ficha desde el catalogo.
2. Regresa y cambia la disponibilidad.
3. Abre nuevamente la misma ficha.
4. Comprueba que el QR conserva la direccion, pero la ficha muestra el dato actualizado.
5. Agrega un nuevo registro.
6. Revisa en Atlas que el documento aparezca en `catalogo_qr > productos`.
7. Prueba una direccion inexistente para observar el mensaje de control.

## 4. Subir a GitHub

Sube todos los archivos excepto `.env`. El archivo `.gitignore` ya evita que las credenciales se agreguen por accidente.

## 5. Desplegar en Render

En Render crea un **Web Service** desde el repositorio de GitHub.

| Configuracion | Valor |
|---|---|
| Language | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app` |

En **Environment** agrega:

| Variable | Valor |
|---|---|
| `MONGO_URI` | Cadena completa de MongoDB Atlas |
| `MONGO_DB` | `catalogo_qr` |
| `SECRET_KEY` | Una frase larga y privada |

Guarda los cambios y realiza el despliegue.

## 6. QR en el celular

En la computadora, `localhost` solamente funciona en esa misma computadora. Para escanear el QR con un celular, utiliza la aplicacion publicada en Render.

Si el QR publicado no contiene la direccion correcta, agrega en Render:

```env
APP_BASE_URL=https://nombre-de-tu-aplicacion.onrender.com
```

## Como adaptarlo a otro proyecto

Los alumnos pueden cambiar los productos por:

- Libros.
- Equipos.
- Eventos.
- Habitaciones.
- Servicios.
- Pedidos.
- Reservaciones.

La idea se conserva: cada documento tiene un `_id`, ese identificador forma una direccion y el QR abre la ficha correspondiente.

## Errores frecuentes

### Aparece la pantalla "Agrega la conexion"

Falta crear el archivo `.env` o no se escribio `MONGO_URI`.

### Atlas no permite la conexion

Revisa usuario, contrasena y Network Access. Si la contrasena contiene caracteres especiales, utiliza una contrasena alfanumerica para la practica o codifica esos caracteres correctamente.

### Render inicia, pero la verificacion falla

Comprueba que `MONGO_URI` exista en **Environment** y que Atlas permita las direcciones de salida de Render.

### El QR no aparece

La imagen QR se obtiene de `api.qrserver.com`; se necesita conexion a Internet.
