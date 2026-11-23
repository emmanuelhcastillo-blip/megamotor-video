# APIs gratis y cómo conseguirlas

Nunca pegues claves en el chat ni en el repo. Van en `.env` (ignorado por git).

## 1. Groq · transcripción (GROQ_API_KEY)
1. Entra a https://console.groq.com con tu correo o Google.
2. **API Keys → Create API Key**, cópiala a `.env` como `GROQ_API_KEY=...`.
3. Cuotas gratis (marzo 2026, pueden cambiar): Whisper large-v3 y large-v3-turbo con 20 peticiones/min, 2.000/día y unas 2 horas de audio por hora. Archivo máximo 25 MB en plan gratis (el motor manda mp3 mono a 32 kbps y trocea los videos largos).
4. Sin clave: `transcribe --local` usa faster-whisper (`pip install faster-whisper`), más lento en 2 CPU.

## 2. Instagram Graph API · publicar y comentar (IG_ACCESS_TOKEN, IG_USER_ID)
Es gratis. Requisitos:
1. Cuenta de Instagram **Profesional** (Creador o Empresa): Instagram → Configuración → Tipo de cuenta.
2. Cuenta de desarrollador en https://developers.facebook.com y una **app** (tipo Empresa).
3. Añadir el producto **Instagram** a la app y, en modo desarrollo, agregarte como administrador/probador.
4. Permisos: `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_comments`.
5. Generar el token de usuario de Instagram y el `IG_USER_ID`; ponerlos en `.env`.
Notas: el modo desarrollo suele alcanzar para publicar en tu propia cuenta sin revisión de Meta (confirmar en la primera prueba). Hay un límite de publicaciones por día (`GET /<IG_ID>/content_publishing_limit`) y unas 200 llamadas por hora por app. Los tokens caducan; hay que renovarlos.
Documentación: https://developers.facebook.com/docs/instagram-platform/content-publishing

## 3. Opcionales
- **Ollama** (local, gratis) para selección de clips sin enviar nada fuera.
- **Wikimedia Commons / Pexels / Pixabay** para imágenes y b-roll con licencia libre (Pexels y Pixabay piden una clave gratuita).
- **ElevenLabs** solo si hace falta locución sintética (tiene capa gratis limitada).
