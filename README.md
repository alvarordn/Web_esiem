# ESIEM · Plataforma web y CRM

Web pública y CRM del **Encuentro Sobre Ingeniería y Empleo** (ETSi, Universidad de Sevilla). Especificación funcional en `especificaciones_del_proyecto.md`.

## Puesta en marcha (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo        # opcional: datos y usuarios de demostración
.\.venv\Scripts\python manage.py runserver
```

- Web pública: http://127.0.0.1:8000/
- Área privada (CRM / portal del expositor): http://127.0.0.1:8000/panel/
- Administración Django (fecha, clave de invitación, carta del director, programa, coste y datos de pago): http://127.0.0.1:8000/admin/

`seed_demo` crea 33 empresas confirmadas con sus logos de `estilo/Empresas` y dos usuarios de prueba (se muestran por consola).

Organizadores, cátedras, redes sociales y cifras de la ETSi se editan en `core/content.py` (logos en `static/img/`). Para un superusuario propio: `manage.py createsuperuser` (los superusuarios tienen acceso completo al CRM).

## Tests

```powershell
.\.venv\Scripts\python manage.py test                       # todos
.\.venv\Scripts\python manage.py test crm.tests.EmailTests  # una clase
```

## Configuración (variables de entorno)

También pueden escribirse en un archivo `.env` en la raíz (no se versiona; plantilla en `.env.example`). Las variables de entorno reales tienen prioridad. Para el correo de la US: `mail.us.es`, puerto 587, STARTTLS, usuario `usuario@us.es` y clave UVUS. Prueba de envío: `manage.py sendtestemail destinatario@ejemplo.es`. Tras editar `.env`, reinicia `runserver`.

| Variable | Uso |
|---|---|
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | Ajustes de despliegue |
| `ESIEM_SMTP_HOST`, `ESIEM_SMTP_PORT`, `ESIEM_SMTP_USER`, `ESIEM_SMTP_PASSWORD`, `ESIEM_SMTP_TLS` | Cuenta SMTP oficial. Sin `ESIEM_SMTP_HOST` los correos se imprimen en la consola |
| `ESIEM_FROM_EMAIL` | Remitente de los correos |
| `ESIEM_EMAIL_AUTOMATIC` | `false` = el CRM no envía; abre el correo en Outlook (web o app) y el organizador registra el envío. Necesario con el correo de la US mientras el SIC no habilite el envío desde aplicaciones |

La **clave común de invitación**, la fecha del evento (cuenta atrás), la carta del director y el **año de la edición** se editan en *Admin → Configuración del evento*. Cada registro del CRM (empresas, contactos, anotaciones, correos, asistentes, materiales, objetivos y registro de organización) guarda en el campo «año de ESIEM» el año de la edición vigente al crearse (2027).

## Plantillas de correo

Archivos `.txt` en `email_templates/`. La primera línea `Asunto: …` es el asunto. Variables disponibles: `{nombre_empresa}`, `{enlace_registro}`, `{clave_registro}`, `{enlace_acceso}`, `{nombre_evento}`, `{fecha_evento}`, `{lugar_evento}`, `{stand}`, `{nombre_contacto}` y, en el correo de aceptación, `{usuario}` y `{contraseña}`. Cualquier `.txt` nuevo aparece automáticamente en el desplegable del CRM.

## Alta de empresas

1. La invitación (con la clave común) se envía por correo fuera de la aplicación (`email_templates/invitacion.txt` sirve de texto base).
2. La empresa introduce la clave en *Formulario de participación* y envía sus datos: entra en el CRM como **Interesada**.
3. En su ficha del CRM, *Aceptar* o *Rechazar* prepara el correo correspondiente (`aceptacion.txt` / `rechazo.txt`). Al enviarlo (o registrar que se ha enviado desde Outlook) la empresa pasa a **Aceptada** o **Rechazada**. La aceptación crea su usuario del portal (derivado del nombre de la empresa) con una contraseña aleatoria, ambos incluidos en el correo y visibles en la ficha para poder reenviarlos.

Solo las empresas *Aceptadas* aparecen en la página pública «Empresas».

## Pendiente antes de producción

- Revisar los textos legales (`templates/core/legal/`) con el responsable de protección de datos.
- Sustituir Tailwind por CDN por un CSS compilado: el binario autónomo de Tailwind (sin Node) puede generar `static/css/tailwind.css` a partir de las plantillas.
- Servir `media/` desde el servidor web y no desde Django; los SVG subidos por empresas deberían servirse con `Content-Disposition: attachment` o desde otro dominio.
- Tipografía: el manual usa *Myriad Variable Concept* (de pago); la web usa Myriad Pro si está instalada y, si no, *Barlow Semi Condensed* como alternativa libre.
