from __future__ import annotations

from datetime import datetime


DEFAULT_LEGAL_UPDATED_AT = datetime(2026, 7, 1)

DEFAULT_LEGAL_DOCUMENTS: dict[str, dict[str, str]] = {
    "terms": {
        "title": "Términos de Servicio",
        "content": """Última actualización: Julio 2026

Estos Términos de Servicio regulan el acceso y uso de GovRadar, la plataforma SaaS operada por Rodar Consulting S.A.C. (en adelante, “la Empresa”). Al ingresar, el usuario confirma que cuenta con autorización de su organización y acepta estas condiciones.

## 1. Alcance del servicio
GovRadar facilita el monitoreo de procesos de contratación pública, la priorización de oportunidades y el envío de alertas configuradas por el usuario. La plataforma consolida información de fuentes públicas, pero no reemplaza la consulta de los portales oficiales ni garantiza la adjudicación, vigencia o integridad de un proceso.

## 2. Cuenta y acceso autorizado
El usuario debe mantener sus credenciales bajo reserva, proporcionar datos de cuenta correctos y notificar cualquier acceso no autorizado. Cada cuenta debe utilizarse exclusivamente para los fines comerciales lícitos de la organización autorizada.

## 3. Configuración y uso responsable
El usuario es responsable de las palabras clave, reglas de alerta, destinatarios y criterios de seguimiento que configure. Antes de tomar decisiones comerciales deberá validar fechas, requisitos y documentos en la fuente oficial.

## 4. Disponibilidad y evolución
La Empresa aplica esfuerzos razonables para mantener el servicio disponible y seguro. Durante la fase de validación pueden realizarse mejoras, mantenimientos o ajustes que modifiquen temporalmente alguna funcionalidad.

## 5. Privacidad y confidencialidad
El tratamiento de datos se rige por la Política de Privacidad. Las estrategias, búsquedas y oportunidades del cliente se protegen conforme a la Cláusula de Confidencialidad de Datos Comerciales y Gubernamentales.

## 6. Propiedad intelectual
El software, la interfaz, la marca y los componentes propios de GovRadar pertenecen a la Empresa. Los datos provenientes de organismos públicos conservan la titularidad y condiciones de sus fuentes de origen.

## 7. Suspensión o terminación
La Empresa podrá restringir el acceso ante usos ilícitos, intentos de vulneración, divulgación de credenciales o incumplimientos graves. La terminación no extingue las obligaciones de confidencialidad aplicables.

## 8. Actualizaciones y contacto
Estos términos podrán actualizarse para reflejar cambios funcionales o normativos, indicando siempre su fecha de revisión. Las consultas pueden enviarse a privacidad@rodar.pe.""",
    },
    "privacy": {
        "title": "Política de Privacidad",
        "content": """Última actualización: Julio 2026

Rodar Consulting S.A.C. (en adelante, “la Empresa”) está comprometida con la seguridad y privacidad de la información de sus usuarios. Esta política describe cómo tratamos los datos dentro de nuestra plataforma SaaS.

## A. Datos recopilados
- Datos de cuenta: nombres, correos electrónicos, cargos y datos de contacto de los usuarios autorizados.
- Datos de operación: información sobre procesos, licitaciones, alertas y palabras clave que el usuario configura o gestiona dentro del CRM.

## B. Finalidad del tratamiento
Los datos recopilados se utilizan exclusivamente para:
- Proveer, operar y mantener las funcionalidades de la plataforma.
- Enviar alertas automáticas y notificaciones configuradas por el usuario.
- Brindar soporte técnico y optimizar la experiencia durante esta fase de validación.

## C. Seguridad de la información
Implementamos medidas técnicas y organizativas estándar de la industria, como cifrado de datos en tránsito y controles de acceso restringido, para proteger la información contra accesos no autorizados, pérdida o alteración.

## D. Derechos ARCO
Los usuarios pueden ejercer sus derechos de Acceso, Rectificación, Cancelación y Oposición sobre sus datos de cuenta mediante una solicitud formal a privacidad@rodar.pe.""",
    },
    "confidentiality": {
        "title": "Cláusula de Confidencialidad",
        "content": """## Reconocimiento de información sensible
Rodar Consulting S.A.C. reconoce que los criterios de búsqueda, palabras clave, estrategias de seguimiento, analítica de mercado y asignación de oportunidades comerciales configuradas por el usuario dentro de la plataforma constituyen Información Confidencial y de alto valor estratégico para el negocio del cliente.

## Compromiso de no divulgación
La Empresa se compromete estrictamente a:
- No vender, comercializar, transferir ni divulgar a terceros —incluidos otros clientes o competidores— información, reportes o estrategias extraídas de la actividad del usuario.
- Mantener absoluta reserva sobre los procesos específicos del Estado, incluidos SEACE, Mercado Público, OCDS y contratos, que el cliente monitorea activamente o gestiona en su embudo comercial.
- Utilizar datos agregados y completamente anonimizados únicamente con fines estadísticos globales de rendimiento del software, sin permitir la identificación del cliente ni de sus objetivos comerciales.

Esta obligación de confidencialidad permanecerá vigente durante todo el periodo de uso del SaaS y se mantendrá de forma indefinida tras la terminación del servicio.""",
    },
}
