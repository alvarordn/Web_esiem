# Especificaciones del Proyecto: Plataforma Web y CRM para Feria de Empleo (Estilo ESIEM)

## 1. Visión General del Proyecto
Desarrollo de una plataforma web integral para la gestión de una Feria de Empleo y Talento Universitario. El sistema debe permitir la gestión de marcas expositoras, comunicación tipo CRM con las empresas, logística de asistencia, catalogación pública de participantes y un área privada simétrica tanto para organizadores (administradores) como para empresas.

- **Backend:** Django (Python) con Django REST Framework para la gestión de API, lógica de negocio y base de datos.
- **Frontend Público y Privado:** JavaScript (ES6+), HTML5, CSS3 / Tailwind CSS para la interfaz interactiva.
- **Identidad Corporativa:** Pendiente de definir colores, tipografías y branding por parte del cliente (se integrará mediante variables CSS / sistema de diseño).

---

## 2. Arquitectura de Roles y Seguridad

### Roles de Usuario
1. **Visitante / Estudiante (Público):** Acceso sin autenticación al catálogo de empresas, historia del evento, información general y cuenta atrás.
2. **Empresa / Expositor (Área Privada):** Gestión del perfil de su empresa, personal asistente y documentación del stand.
3. **Administrador / Organizador (CRM Privado):** Control total sobre la base de datos de empresas, bitácora de anotaciones, importación de contactos, edición directa de datos y módulo de envío de correos.

### Mecanismo Cortafuegos de Registro (Clave Común de Invitación)
- El registro de empresas en la web pública **no es abierto a cualquier usuario**.
- Se utiliza una **clave común de invitación** (configurada por la administración, ej. `ESIEM-EXPOSITOR-2027`).
- La clave se envía en el correo de invitación a las empresas.
- Durante el registro, si el usuario no introduce la clave correcta, el backend en Django rechaza la creación de la cuenta.

---

## 3. Zona Pública (Web Institucional / Landing)
Páginas e interfaces accesibles sin autenticación:

1. **Home / Landing Principal:**
   - Hero Section con título, fecha del evento y **contador regresivo (countdown)** en tiempo real.
   - Resumen en cifras de ediciones pasadas.
   - Enlaces a la carta de bienvenida y accesos principales.
2. **Carta del Director / Comité Organizador:** Mensaje institucional sobre los objetivos y valores del encuentro.
3. **Directorio Público de Empresas:**
   - Filtro dinámico por sector (ej. IT, Consultoría, Energía, Aeroespacial).
   - Buscador de texto en tiempo real.
   - Tarjetas de empresas expositoras con logo, resumen y sector.
4. **Ediciones Anteriores (Histórico):** Resumen de años pasados, estadísticas de inserción laboral y trayectoria.
5. **Formulario Abierto de Contacto / Solicitud de Información.**
6. **Aviso Legal, Cookies y Privacidad.**

---

## 4. Área Privada de Administrador (CRM del Organizador)

La interfaz del administrador se centra en una **Ficha 360º de Empresa** que permite seleccionar cualquier empresa de la base de datos mediante un desplegable/buscador superior.

### A. Importación Masiva de Datos
- **Carga vía Excel (`.xlsx` / `.csv`):** Subida masiva de datos de empresas.
- **Soporte Múltiple Contacto (Relación 1 a N):** Permite que una misma empresa tenga múltiples correos y personas de contacto (ej. RRHH, Director de Talento, Técnico). Si la empresa ya existe, añade el nuevo contacto sin duplicar la entidad principal.

### B. Pestaña 1: "Resumen & Bitácora"
- **Datos Generales:** CIF, sector, web y contacto principal.
- **Cuadro de Anotaciones CRM:** Campo de texto para redactar novedades (ej. *"Llamada telefónica: aceptan participar"*).
- **Histórico (Timeline):** Registro cronológico donde cada nota muestra **Fecha, Hora exactas, Usuario autor y Texto**.
- **Módulo de envío de correo:** Integrado en la propia pestaña con borrador por defecto para consultas o seguimiento general.

### C. Pestaña 2: "Enviar Invitación"
- **Selección de Destinatarios:** Checkboxes con la lista de correos asociados a esa empresa para marcar a cuáles enviar la invitación.
- **Carga de Plantillas desde `.txt`:** Menú desplegable para cargar plantillas de texto en formato `.txt` almacenadas en el servidor.
- **Variables dinámicas:** Reemplazo automático de etiquetas como `{nombre_empresa}`, `{enlace_registro}` y la **clave común de registro**.
- **Editor en Tiempo Real:** El texto cargado en el cuadro se puede editar libremente antes de pulsar el botón de envío.
- **Botón de Envío:** Integrado con la cuenta SMTP oficial.
- **Historial de Envíos:** Muestra qué correos se enviaron, a quién y en qué fecha/hora.

### D. Pestaña 3: "Personas que asistirán al evento"
- Visualización y **edición directa** por parte del admin del equipo de la empresa que acudirá al evento.
- Formulario para añadir/modificar personal: Nombre, Apellidos, DNI, Cargo, Email, Teléfono y necesidades dietéticas/alérgenos para catering.
- Módulo de envío de correo integrado con **borrador `.txt` por defecto orientado a solicitar la lista de asistentes**.

### E. Pestaña 4: "Dossier y Stand"
- Visualización, descarga y **edición/reemplazo directo** por el admin de los materiales corporativos (Dossier PDF, Logo en alta resolución PNG/SVG, Banners).
- Gestión del número de stand asignado y necesidades logísticas (enchufes, sillas, conexiones Wi-Fi).
- Módulo de envío de correo integrado con **borrador `.txt` por defecto orientado a solicitar materiales de branding o resolver dudas logísticas**.

---

## 5. Área Privada de Empresa (Portal del Expositor)

El área de la empresa es **simétrica** a la del administrador (con la excepción de la pestaña "Enviar Invitación"). Todo cambio realizado por la empresa se refleja en tiempo real en el panel del administrador.

1. **Pestaña "Personas que asistirán al evento":**
   - Formulario para inscribir a los representantes que acudirán al stand.
   - Modificación o eliminación de personal registrado.
   - Indicación de alergias o menú para catering.
2. **Pestaña "Dossier y Stand":**
   - Subida y actualización del Dossier PDF corporativo.
   - Subida del Logotipo en alta calidad y elementos de branding.
   - Formulario de requerimientos para el stand y consulta de la ubicación asignada.

---

## 6. Modelo de Datos Proyectado (Django Models)

### Entidades Principales:
1. `User` (AbstractUser) -> Roles (`is_company`, `is_staff_admin`).
2. `Company` -> Nombre, CIF, sector, sitio web, estado (`prospect`, `invited`, `confirmed`, `declined`), stand asignado.
3. `CompanyContact` (FK a Company) -> Nombre, email, teléfono, cargo, es_principal. (Relación 1-N).
4. `CRMNote` (FK a Company) -> Autor (User), fecha/hora (auto_now_add), texto de la nota, tipo de interacción.
5. `EventAttendee` (FK a Company) -> Nombre, apellidos, DNI, cargo, email, alergias/catering.
6. `CompanyDocumentation` (OneToOne a Company) -> Dossier PDF, Logo Image/Vector, necesidades electromecánicas/stand.
7. `EmailHistory` (FK a Company) -> Asunto, cuerpo enviado, destinatarios, fecha/hora, plantilla utilizada.

---

## 7. Próximos Pasos Pendientes
- Recibir por parte del usuario el manual de identidad corporativa final (paleta de colores Hex, tipografías y logotipo) para su adaptación visual.
- Proceder con el desarrollo de los scripts de importación de Excel y configuración del backend en Django.