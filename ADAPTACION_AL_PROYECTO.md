# Adaptacion al proyecto de cada equipo

No es necesario copiar la cafeteria. Cada equipo debe identificar un documento real de su aplicacion.

| Proyecto | Documento que puede tener QR | Dato que puede actualizarse |
|---|---|---|
| Biblioteca | Libro | Disponible o prestado |
| Inventario | Equipo | Ubicacion o estado |
| Eventos | Evento | Lugar, fecha o cupo |
| Hotel | Habitacion | Disponible u ocupada |
| Restaurante | Producto o pedido | Disponible o entregado |
| Tienda | Producto | Existencia |
| Reservaciones | Reserva | Pendiente, confirmada o cancelada |

## Funcionamiento que deben conservar

1. MongoDB crea un identificador `_id` para cada documento.
2. La aplicacion forma una direccion con ese identificador.
3. El QR guarda la direccion.
4. Al abrir la ficha, Flask busca el documento en MongoDB.
5. La ficha muestra la informacion actual.

## Informacion que no debe ser publica

- Contrasenas.
- Domicilios particulares.
- Telefonos personales.
- Correos privados.
- Datos medicos.
- Informacion bancaria.

El QR debe abrir solamente una ficha con los datos necesarios para el uso del proyecto.
