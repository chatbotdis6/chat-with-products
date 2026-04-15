# Batería de Pruebas WhatsApp — Chat with Products

> **Fecha inicio**: 10 de abril de 2026  
> **Versión actual**: v15  
> **Entorno**: Streamlit local + LLM real + DB real

---

## Bloque 1 — Conversacional básico
> Verifica saludos, preguntas sobre el servicio, confirmaciones sin contexto, despedidas.

- [x] `/reset`
- [x] **"Hola"** → Saludo + presentación del servicio
- [x] **"Qué productos manejas?"** → Explicación del servicio (NO "fuera del sector")
- [x] **"Sí por favor"** → Pide especificar qué producto busca (NO repite saludo)
- [x] **"Gracias"** → Despedida cordial

✅ **Completado** — v12

---

## Bloque 2 — Búsqueda + filtro marca + precio + show_more + detalle
> Flujo completo de búsqueda con filtros encadenados.

- [x] `/reset`
- [x] **"Busco aceite de oliva"** → Muestra marcas disponibles y pregunta preferencia de marca
- [x] **"De la marca Carbonell"** → Muestra proveedor(es) con Carbonell
- [x] **"A qué precios?"** → Muestra precios de aceite de oliva Carbonell
- [x] **"Quiero ver más proveedores"** → Dice que solo hay La Ranita De La Paz
- [x] **"Dame el detalle del primero"** → Muestra tarjeta de detalle + aviso de plataforma

✅ **Completado** — v16

---

## Bloque 3 — Producto no registrado
> Verifica que un producto que NO existe en la BD se maneje correctamente.

- [x] `/reset`
- [x] **"Busco caviar beluga"** → Mensaje de "no lo tenemos" + aviso de que se contactará en 12h

✅ **Completado** — v17

---

## Bloque 4 — Especialistas
> Verifica que las preguntas de especialista se deriven correctamente.

- [x] `/reset`
- [x] **"¿Cómo hago una salsa bechamel?"** → Respuesta del Chef
- [x] **"¿Cuántas calorías tiene el aceite de oliva?"** → Respuesta del Nutriólogo
- [x] **"¿Cómo preparo un mojito?"** → Respuesta del Bartender
- [x] **"¿Cuál es el mejor método para preparar café de especialidad?"** → Respuesta del Barista
- [x] **"¿Cómo conservo la carne fresca más tiempo?"** → Respuesta del Ingeniero de Alimentos

✅ **Completado** — v18

---

## Bloque 5 — Derivación a plataforma (turnos progresivos)
> Verifica que las sugerencias de plataforma aparezcan en los turnos correctos.

- [x] `/reset`
- [x] **Turn 0**: "Busco harina" → Resultados normales (sin mención de plataforma)
- [x] **Turn 1**: "De la marca Tres Estrellas" → Resultados normales (sin mención)
- [x] **Turn 2**: "Busco azúcar" → Resultados normales (sin mención)
- [x] **Turn 3**: "Busco mantequilla" → Resultados normales (sin mención)
- [x] **Turn 4**: "Busco leche" → Resultados + **"📢 ¡Importante! Ya llevamos varias consultas..."**
- [x] **Turn 5+**: "Busco café" → **Plantilla fija** sin LLM (platform_exhausted=true)

---

## Bloque 6 — Usuario difícil
> Verifica el manejo de usuarios con comportamiento problemático.

- [x] `/reset`
- [x] **"Esto es una mierda de servicio"** → Respuesta empática (queja/insulto), no se bloquea
- [x] **"Eres un inútil"** → Respuesta calmada, ofrece ayuda
- [x] **"Quiero hablar con un humano"** → Respuesta de atención, ofrece alternativas

✅ **Completado** — v19

---

## Bloque 7 — Mensajes concurrentes (race condition)
> Verifica que dos mensajes rápidos seguidos no causen saludos duplicados ni errores.

- [x] `/reset`
- [x] **Enviar "Hola" e inmediatamente "Busco aceite"** (< 1 segundo entre ambos)
- [x] Verificar que NO hay doble saludo
- [x] Verificar que ambos mensajes se procesan en orden
- [x] Verificar que no hay error 500 en logs

✅ **Completado** — v20 (WhatsApp + Heroku)

---

## Bloque 8 — Edge cases
> Casos borde para robustez general.

- [x] `/reset`
- [x] **Mensaje muy largo (500+ caracteres)** → Se procesa sin error
- [x] **Emojis solos "👍"** → Redirige a su alcance gastronómico
- [x] **Número suelto "3"** → Redirige a su alcance gastronómico
- [x] **"Busco algo" (producto genérico)** → Pide especificar
- [x] **"Cuánto es 2+2?"** → NO responde, redirige a su alcance
- [x] **"Qué tiempo hace en Madrid?"** → NO responde, redirige a su alcance

✅ **Completado** — v21 (WhatsApp + Heroku)

---

## Resumen de progreso

| Bloque | Descripción | Estado |
|--------|------------|--------|
| 1 | Conversacional básico | ✅ Completado (v12) |
| 2 | Búsqueda + filtros encadenados | ✅ Completado (v16) |
| 3 | Producto no registrado | ✅ Completado (v17) |
| 4 | Especialistas | ✅ Completado (v18) |
| 5 | Derivación a plataforma | ✅ Completado (v19) |
| 6 | Usuario difícil | ✅ Completado (v19) |
| 7 | Mensajes concurrentes | ✅ Completado (v20) |
| 8 | Edge cases | ✅ Completado (v21) |
